# Shared scorer source attribution

`src/sentiment/__init__.py`, `src/sentiment/finbert_scorer.py`, and `src/storage.py` are unchanged copies from the team IndicatorLab reddit branch, commit `ca3d391cd596a08af6d7ea290563c2fb1712fda9`. They retain the repository MIT license and existing copyright notices.

The scorer SHA-256 is `8663385349511360891a2a4524aa7ca98a4cce61e197284c5b532bc86b5d373b`. Week4 uses its preprocessing and batched probability implementation directly. The model is ProsusAI/finbert, revision `0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031`, loaded from the existing local model directory without a new download. The model weights are not part of the Git contribution.

Prior Week3 scoring outputs remain archived. New Week4 sentiment outputs are distinct prepared inputs under the new cutoff; no claim of having posted them to a shared sheet is made.
