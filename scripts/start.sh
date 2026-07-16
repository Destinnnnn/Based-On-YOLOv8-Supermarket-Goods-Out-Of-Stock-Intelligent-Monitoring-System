#!/bin/bash
# Startup script for YOLOv8 Stock Monitor System

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$ROOT_DIR"

echo "=========================================="
echo "YOLOv8 Stock Monitor - Startup Script"
echo "=========================================="

# Check if database exists
if [ ! -f "data/stock_monitor.db" ]; then
    echo "Database not found. Initializing..."
    python scripts/init_db.py
fi

# Check if model exists
if [ ! -f "models/best.pt" ]; then
    echo ""
    echo "WARNING: Trained model not found at models/best.pt"
    echo "The system will use the pretrained yolov8n.pt model."
    echo ""
    echo "To train your custom model, run:"
    echo "  python scripts/train_yolov8.py --test    (quick test, 10 epochs)"
    echo "  python scripts/train_yolov8.py           (full training, 100 epochs)"
    echo ""
    read -p "Press Enter to continue with pretrained model..."
fi

# Start backend server
echo ""
echo "Starting backend server..."
echo "API will be available at: http://localhost:8000"
echo "API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
