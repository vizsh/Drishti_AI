# data/

Gitignored. Local-only: staged test footage, downloaded datasets, model
weights (`.pt`/`.onnx`/`.engine`). Never commit real or staged exam footage
here even accidentally — check `.gitignore` before adding new file types.

- `raw/` — unprocessed source footage (staged recordings, sample clips)
- `staged/` — footage filmed specifically for training/testing (own volunteers, own camera/room)
- `weights/` — downloaded/fine-tuned model checkpoints
