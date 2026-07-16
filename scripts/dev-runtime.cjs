const fs = require('fs');
const http = require('http');
const https = require('https');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const rootDir = path.resolve(__dirname, '..');
const runtimeDir = path.join(rootDir, '.runtime');
const condaEnvName = 'env1';

const runtimePaths = {
  backendPidFile: path.join(runtimeDir, 'backend.pid'),
  frontendPidFile: path.join(runtimeDir, 'frontend.pid'),
  backendOutLog: path.join(runtimeDir, 'backend.out.log'),
  backendErrLog: path.join(runtimeDir, 'backend.err.log'),
  frontendOutLog: path.join(runtimeDir, 'frontend.out.log'),
  frontendErrLog: path.join(runtimeDir, 'frontend.err.log'),
  legacyBackendLauncher: path.join(runtimeDir, 'launch_backend.cmd'),
  legacyFrontendLauncher: path.join(runtimeDir, 'launch_frontend.cmd'),
};

function ensureRuntimeDir() {
  fs.mkdirSync(runtimeDir, { recursive: true });
}

function getCommandHost() {
  return process.env.ComSpec || 'C:\\Windows\\System32\\cmd.exe';
}

function buildPythonPath() {
  return [
    path.join(rootDir, '.pydeps'),
    path.join(rootDir, 'backend'),
    process.env.PYTHONPATH || '',
  ]
    .filter(Boolean)
    .join(path.delimiter);
}

function buildEnv(extraEnv = {}) {
  return {
    ...process.env,
    CONDA_NO_PLUGINS: 'true',
    PYTHONPATH: buildPythonPath(),
    ...extraEnv,
  };
}

function findCommand(candidates, whereTarget) {
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  const whereResult = spawnSync('where', [whereTarget], {
    encoding: 'utf8',
  });

  if (whereResult.status === 0) {
    const firstMatch = whereResult.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find(Boolean);

    if (firstMatch) {
      return firstMatch;
    }
  }

  return null;
}

function findCondaCommand() {
  return findCommand(
    ['D:\\anaconda3\\Scripts\\conda.exe', 'D:\\anaconda3\\Library\\bin\\conda.bat'],
    'conda'
  );
}

function findNpmCommand() {
  return findCommand(['D:\\nodeJS\\npm.cmd'], 'npm');
}

function quoteForCmd(value) {
  const stringValue = String(value);
  if (!/[ \t"&()^%!]/.test(stringValue)) {
    return stringValue;
  }

  return `"${stringValue.replace(/"/g, '""')}"`;
}

function buildCommandLine(command, args) {
  return [quoteForCmd(command), ...args.map((arg) => quoteForCmd(arg))].join(' ');
}

function isCmdScript(command) {
  return /\.(cmd|bat)$/i.test(command);
}

function runCommand(command, args, options = {}) {
  const baseOptions = {
    encoding: 'utf8',
    stdio: 'pipe',
    ...options,
    env: buildEnv(options.env),
  };

  if (isCmdScript(command)) {
    return spawnSync(getCommandHost(), ['/d', '/s', '/c', buildCommandLine(command, args)], baseOptions);
  }

  return spawnSync(command, args, baseOptions);
}

function assertCondaEnvReady(condaCommand, envName) {
  let result = runCommand(condaCommand, ['run', '-n', envName, 'python', '-c', 'import sys']);
  if (result.status !== 0) {
    throw new Error(
      `Conda environment '${envName}' is not ready. Try: conda run -n ${envName} python -c "import sys"`
    );
  }

  result = runCommand(condaCommand, [
    'run',
    '-n',
    envName,
    'python',
    '-c',
    'import sqlalchemy, uvicorn, websockets, wsproto, httptools',
  ]);
  if (result.status !== 0) {
    throw new Error(
      `Conda environment '${envName}' is missing runtime dependencies. Try: conda run -n ${envName} python -c "import sqlalchemy, uvicorn, websockets, wsproto, httptools"`
    );
  }
}

function runCondaPythonScript(condaCommand, envName, scriptPath) {
  return runCommand(condaCommand, ['run', '-n', envName, 'python', scriptPath]);
}

function removeFileIfExists(filePath) {
  try {
    fs.rmSync(filePath, { force: true });
  } catch {
  }
}

function readPid(filePath) {
  if (!fs.existsSync(filePath)) {
    return null;
  }

  const rawValue = fs.readFileSync(filePath, 'utf8').trim();
  return /^\d+$/.test(rawValue) ? Number(rawValue) : null;
}

function killPid(pid) {
  try {
    process.kill(pid);
    return true;
  } catch {
    return false;
  }
}

function stopManagedProcesses({ quiet = false } = {}) {
  ensureRuntimeDir();

  for (const pidFile of [runtimePaths.backendPidFile, runtimePaths.frontendPidFile]) {
    const pid = readPid(pidFile);
    if (pid) {
      killPid(pid);
    }
    removeFileIfExists(pidFile);
  }

  removeFileIfExists(runtimePaths.legacyBackendLauncher);
  removeFileIfExists(runtimePaths.legacyFrontendLauncher);

  if (!quiet) {
    console.log('Managed frontend/backend processes have been stopped.');
  }
}

function cleanupRuntimeFiles() {
  for (const filePath of [
    runtimePaths.backendOutLog,
    runtimePaths.backendErrLog,
    runtimePaths.frontendOutLog,
    runtimePaths.frontendErrLog,
    runtimePaths.backendPidFile,
    runtimePaths.frontendPidFile,
    runtimePaths.legacyBackendLauncher,
    runtimePaths.legacyFrontendLauncher,
  ]) {
    removeFileIfExists(filePath);
  }
}

function startDetachedProcess(command, args, { cwd, stdoutPath, stderrPath, env = {} }) {
  const stdoutFd = fs.openSync(stdoutPath, 'a');
  const stderrFd = fs.openSync(stderrPath, 'a');

  try {
    const child = isCmdScript(command)
      ? spawn(getCommandHost(), ['/d', '/s', '/c', buildCommandLine(command, args)], {
          cwd,
          env: buildEnv(env),
          detached: true,
          windowsHide: true,
          stdio: ['ignore', stdoutFd, stderrFd],
        })
      : spawn(command, args, {
          cwd,
          env: buildEnv(env),
          detached: true,
          windowsHide: true,
          stdio: ['ignore', stdoutFd, stderrFd],
        });

    child.unref();
    return child;
  } finally {
    fs.closeSync(stdoutFd);
    fs.closeSync(stderrFd);
  }
}

function getListeningProcessId(port) {
  const result = spawnSync('netstat', ['-ano'], {
    encoding: 'utf8',
  });

  if (result.status !== 0) {
    return null;
  }

  const targetPattern = new RegExp(`:${port}\\s`);
  for (const line of result.stdout.split(/\r?\n/)) {
    if (!line.includes('LISTENING') || !targetPattern.test(line)) {
      continue;
    }

    const parts = line.trim().split(/\s+/);
    const pidCandidate = parts[parts.length - 1];
    if (/^\d+$/.test(pidCandidate)) {
      return Number(pidCandidate);
    }
  }

  return null;
}

function waitForUrl(url, timeoutSeconds = 60) {
  const urlObject = new URL(url);
  const requestModule = urlObject.protocol === 'https:' ? https : http;
  const deadline = Date.now() + timeoutSeconds * 1000;

  return new Promise((resolve) => {
    const tryOnce = () => {
      const request = requestModule.get(
        urlObject,
        { timeout: 3000 },
        (response) => {
          response.resume();
          if (response.statusCode && response.statusCode >= 200 && response.statusCode < 500) {
            resolve(true);
            return;
          }

          if (Date.now() >= deadline) {
            resolve(false);
            return;
          }

          setTimeout(tryOnce, 750);
        }
      );

      request.on('error', () => {
        if (Date.now() >= deadline) {
          resolve(false);
          return;
        }

        setTimeout(tryOnce, 750);
      });

      request.on('timeout', () => {
        request.destroy();
      });
    };

    tryOnce();
  });
}

function writePidFile(filePath, pid) {
  fs.writeFileSync(filePath, String(pid), 'ascii');
}

module.exports = {
  buildEnv,
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
  assertCondaEnvReady,
};
