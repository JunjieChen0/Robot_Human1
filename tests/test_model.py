import numpy as np
import pandas as pd

from src.config import FEATURE_NAMES, LABEL_ORDER
from src.train import build_models


def test_both_models_fit_and_return_seven_class_probabilities():
    rng = np.random.default_rng(42)
    rows = []
    labels = []
    for position, label in enumerate(LABEL_ORDER):
        for _ in range(6):
            rows.append(rng.normal(loc=position + 1, scale=0.2, size=len(FEATURE_NAMES)))
            labels.append(label)
    X = pd.DataFrame(rows, columns=FEATURE_NAMES)
    y = pd.Series(labels)

    for model in build_models().values():
        model.fit(X, y)
        probabilities = model.predict_proba(X.iloc[:3])
        assert probabilities.shape == (3, 7)
        assert np.allclose(probabilities.sum(axis=1), 1.0)
