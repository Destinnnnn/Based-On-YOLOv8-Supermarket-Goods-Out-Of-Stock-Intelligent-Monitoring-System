const fs = require('fs');
const path = require('path');
const {
  assertCondaEnvReady,
  cleanupRuntimeFiles,
  condaEnvName,
  ensureRuntimeDir,
  findCondaCommand,
  findNpmCommand,
  getListeningProcessId,
  rootDir,
  runCondaPythonScript,
  runtimeDir,
  runtimePaths,
  startDetachedProcess,
  stopManagedProcesses,
  waitForUrl,
  writePidFile,
} = require('./dev-runtime.cjs');

async function main() {
  ensureRuntimeDir();

  const condaCommand = findCondaCommand();
  if (!condaCommand) {
    throw new Error(
      "Conda was not found. Please install Anaconda/Miniconda and make 'conda' available."
    );
  }

  const npmCommand = findNpmCommand();
  if (!npmCommand) {
    throw new Error("npm was not found. Please install Node.js and make 'npm' available.");
  }

  assertCondaEnvReady(condaCommand, condaEnvName);
  stopManagedProcesses({ quiet: true });

  const databasePath = path.join(rootDir, 'data', 'stock_monitor.db');
  const initDbScript = path.join(rootDir, 'scripts', 'init_db.py');
  const createAdminScript = path.join(rootDir, 'scripts', 'create_admin.py');

  if (!fs.existsSync(databasePath)) {
    console.log('[1/4] Database not found, initializing...');
    const initResult = runCondaPythonScript(condaCommand, condaEnvName, initDbScript);
    if (initResult.status !== 0) {
      console.error('\nDatabase initialization failed.');
      if (initResult.stdout?.trim()) {
        console.error(initResult.stdout.trim());
      }
      if (initResult.stderr?.trim()) {
        console.error(initResult.stderr.trim());
      }
      throw new Error('Database initialization failed.');
    }
  }

  console.log('[2/4] Ensuring admin account exists...');
  const adminResult = runCondaPythonScript(condaCommand, condaEnvName, createAdminScript);
  if (adminResult.status !== 0) {
    console.error('\nAdmin bootstrap failed.');
    if (adminResult.stdout?.trim()) {
      console.error(adminResult.stdout.trim());
    }
    if (adminResult.stderr?.trim()) {
      console.error(adminResult.stderr.trim());
    }
    throw new Error('Admin bootstrap failed.');
  }

  if (!fs.existsSync(path.join(rootDir, 'models', 'best.pt'))) {
    console.log('[3/4] Custom model not found, startup will use yolov8n.pt');
  }
  if (!fs.existsSync(path.join(rootDir, 'weights', 'count_best.pt'))) {
    console.log('[3/4] Count model not found, detection counts will use per-box fallback');
  }

  cleanupRuntimeFiles();

  console.log('[4/4] Starting backend and frontend...');

  startDetachedProcess(
    condaCommand,
    ['run', '-n', condaEnvName, 'python', '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'],
    {
      cwd: path.join(rootDir, 'backend'),
      stdoutPath: runtimePaths.backendOutLog,
      stderrPath: runtimePaths.backendErrLog,
    }
  );

  startDetachedProcess(
    npmCommand,
    ['run', 'dev', '--', '--host', '127.0.0.1', '--port', '3000'],
    {
      cwd: path.join(rootDir, 'frontend'),
      stdoutPath: runtimePaths.frontendOutLog,
      stderrPath: runtimePaths.frontendErrLog,
    }
  );

  const [backendReady, frontendReady] = await Promise.all([
    waitForUrl('http://127.0.0.1:8000/health'),
    waitForUrl('http://127.0.0.1:3000'),
  ]);

  if (!backendReady || !frontendReady) {
    console.error('\nStartup failed. Please inspect:');
    console.error(`  ${runtimePaths.backendErrLog}`);
    console.error(`  ${runtimePaths.frontendErrLog}`);
    stopManagedProcesses({ quiet: true });
    process.exit(1);
  }

  const backendPid = getListeningProcessId(8000);
  const frontendPid = getListeningProcessId(3000);

  if (backendPid) {
    writePidFile(runtimePaths.backendPidFile, backendPid);
  }

  if (frontendPid) {
    writePidFile(runtimePaths.frontendPidFile, frontendPid);
  }

  console.log('\n==========================================');
  console.log('YOLOv8 Stock Monitor is ready');
  console.log('==========================================');
  console.log('Frontend: http://127.0.0.1:3000');
  console.log('Backend : http://127.0.0.1:8000');
  console.log('Docs    : http://127.0.0.1:8000/docs');
  console.log('Admin   : admin / 88888888');
  console.log('');
  console.log('Stop command: npm run stop');
  console.log(`Runtime logs: ${runtimeDir}`);
}

main().catch((error) => {
  console.error('');
  console.error(error.message || error);
  process.exit(1);
});
