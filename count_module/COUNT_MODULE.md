# Count Module

This package estimates the number of products inside each YOLO detection box.
It does not open cameras, decode video, upload files, or run object detection.

## Runtime API

```python
from count_module import CountPredictor

counter = CountPredictor("weights/count_best.pt", device="cuda")
results = counter.predict(
    image,
    [
        {"xyxy": [10, 20, 120, 180], "class_id": 20, "conf": 0.91},
        {"xyxy": [220, 40, 420, 260], "class_id": 34, "conf": 0.87},
    ],
)
```

`image` may be a `numpy.ndarray`, `PIL.Image`, or image path. NumPy arrays
are treated as RGB by default. For OpenCV BGR frames, construct the predictor
with `array_color="BGR"`.

Each detection must contain pixel-level `xyxy` coordinates and a `class_id`.
Other fields are preserved, and the returned detection includes the estimated
`count`.

## Model Checkpoint

The backend loads the default Count checkpoint from:

```text
weights/count_best.pt
```

Model weights are not included in the repository. When the backend checkpoint
is missing or cannot be loaded, runtime detection falls back to a count of 1
for each YOLO box.

## Dependencies

Runtime inference dependencies are included in the root `requirements.txt`.
Training and dataset utilities require the additional packages in:

```bash
pip install -r count_module/requirements-count.txt
```

## Dataset Format

Training data uses one CSV file per split:

```text
datasets/{train,val,test}/counts.csv
```

Each row represents one detection box:

```text
image,class_id,class_name,count,x1,y1,x2,y2
```

Datasets are local assets and are not included in the repository.

## Training And Evaluation

Check dataset consistency:

```bash
python scripts/check_count_dataset.py --data-root datasets
```

Train from ground-truth boxes:

```bash
python scripts/train_count_mbv3.py --data-root datasets --output runtime/runs/count_mbv3_gt_224
```

Generate YOLO-matched boxes for fine-tuning:

```bash
python scripts/generate_count_yoloft_csv.py --data-root datasets --yolo-weights models/best.pt --output-dir runtime/count_yoloft --splits train,val,test
```

Evaluate a checkpoint:

```bash
python scripts/eval_count_mbv3.py --weights weights/count_best.pt --csv datasets/test/counts.csv --image-dir datasets/test/images
```

Run the complete training pipeline:

```bash
bash scripts/run_count_full_pipeline.sh
```

## Integration Example

Run YOLO detection followed by Count inference:

```bash
python examples/count_after_yolo.py --image path/to/image.jpg --yolo-weights models/best.pt --count-weights weights/count_best.pt
```
