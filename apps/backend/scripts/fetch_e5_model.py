"""Download the pinned multilingual-e5-base runtime files once (needs `pip install sentence-transformers`; network only here).

  python scripts/fetch_e5_model.py [target_dir]     # default ~/.cache/elegance/multilingual-e5-base
"""
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"  # intfloat/multilingual-e5-base, as evaluated
FILES = ["config.json", "modules.json", "model.safetensors", "sentence_bert_config.json", "sentencepiece.bpe.model",
         "special_tokens_map.json", "tokenizer_config.json", "tokenizer.json", "1_Pooling/config.json"]

target = sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / ".cache/elegance/multilingual-e5-base")
print(snapshot_download("intfloat/multilingual-e5-base", revision=REVISION, allow_patterns=FILES, local_dir=target))
