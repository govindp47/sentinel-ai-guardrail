from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from typing import Any


def _predict_sync(text: str) -> dict[str, float]:
    """Run detoxify inference synchronously inside a worker process.

    The model is imported and instantiated *inside* this function so the
    object is never pickled across the process boundary — only the text
    string (a primitive) is sent, and only the scores dict is returned.

    This function must remain at module level (not a closure or lambda) so
    that ProcessPoolExecutor can pickle it by reference.

    Args:
        text: input text to score.

    Returns:
        dict mapping detoxify label names to float scores in [0, 1].
    """
    from detoxify import Detoxify

    model = Detoxify("original")
    results: dict[str, Any] = model.predict(text)
    # detoxify returns numpy floats; normalise to Python float for safety
    return {key: float(value) for key, value in results.items()}


class DetoxifyClassifier:
    """Async safety classifier backed by the detoxify ML model.

    Model inference is dispatched to a ``ProcessPoolExecutor`` so the
    asyncio event loop is never blocked by CPU-bound work.

    Usage::

        classifier = DetoxifyClassifier()
        try:
            scores = await classifier.predict("some text")
        finally:
            classifier.shutdown()
    """

    def __init__(self, max_workers: int = 2) -> None:
        """Initialise the classifier and its process pool.

        Args:
            max_workers: number of worker processes in the pool.
                         Each worker will load its own copy of the model
                         on first use.
        """
        self._process_pool: ProcessPoolExecutor = ProcessPoolExecutor(max_workers=max_workers)

    async def predict(self, text: str) -> dict[str, float]:
        """Return toxicity scores for *text*.

        Dispatches to the process pool so the event loop is not blocked.

        Args:
            text: input string to evaluate.

        Returns:
            dict of label → float score in [0, 1], e.g.::

                {
                    "toxicity": 0.001,
                    "severe_toxicity": 0.0,
                    "obscene": 0.0,
                    "threat": 0.0,
                    "insult": 0.001,
                    "identity_attack": 0.0,
                }
        """
        loop = asyncio.get_event_loop()
        scores: dict[str, float] = await loop.run_in_executor(
            self._process_pool, _predict_sync, text
        )
        return scores

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the process pool, optionally waiting for workers.

        Should be called when the classifier is no longer needed (e.g. in
        application shutdown hooks) to release worker processes promptly.

        Args:
            wait: if True (default), block until all workers have exited.
        """
        self._process_pool.shutdown(wait=wait)
