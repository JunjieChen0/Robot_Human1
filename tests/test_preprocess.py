import pandas as pd

from src.config import FEATURE_NAMES, LABEL_COLUMN
from src.preprocess import assign_splits, detect_outliers, encode_features


def raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Age": 25.0,
                "Height": 1.70,
                "Weight": 70.0,
                "FCVC": 2.0,
                "NCP": 3.0,
                "CH2O": 2.0,
                "FAF": 2.0,
                "TUE": 1.0,
                "Gender": "Male",
                "family_history_with_overweight": "yes",
                "FAVC": "no",
                "SMOKE": "no",
                "SCC": "yes",
                "CAEC": "Always",
                "CALC": "no",
                "MTRANS": "Walking",
                LABEL_COLUMN: "Normal_Weight",
            }
        ]
    )


def test_encode_features_maps_categorical_values():
    encoded = encode_features(raw_frame())
    assert list(encoded.columns) == FEATURE_NAMES
    assert encoded.loc[0, "Gender"] == 1.0
    assert encoded.loc[0, "family_history_with_overweight"] == 1.0
    assert encoded.loc[0, "CAEC"] == 3.0
    assert encoded.loc[0, "CALC"] == 0.0
    assert encoded.loc[0, "MTRANS_Walking"] == 1.0
    assert encoded.loc[0, "MTRANS_Bike"] == 0.0


def test_assign_splits_keeps_all_classes_in_every_split():
    rows = []
    for index in range(70):
        row = raw_frame().iloc[0].to_dict()
        row[LABEL_COLUMN] = [
            "Insufficient_Weight",
            "Normal_Weight",
            "Overweight_Level_I",
            "Overweight_Level_II",
            "Obesity_Type_I",
            "Obesity_Type_II",
            "Obesity_Type_III",
        ][index % 7]
        row["Weight"] = 50.0 + index
        rows.append(row)
    frame = encode_features(pd.DataFrame(rows))
    frame.insert(0, LABEL_COLUMN, [row[LABEL_COLUMN] for row in rows])
    result = assign_splits(frame, random_state=7)

    counts = result["split"].value_counts()
    assert counts["train"] == 42
    assert counts["validation"] == 14
    assert counts["test"] == 14
    for split in ("train", "validation", "test"):
        assert result.loc[result["split"].eq(split), LABEL_COLUMN].nunique() == 7


def test_detect_outliers_detects_domain_violations():
    frame = encode_features(raw_frame())
    bad = frame.iloc[0].copy()
    bad["TUE"] = 5.0
    bad["Weight"] = 250.0
    report = detect_outliers(pd.concat([frame, bad.to_frame().T], ignore_index=True))
    assert report["fields"]["TUE"]["out_of_domain"] == 1
    assert report["fields"]["Weight"]["out_of_domain"] == 1
    assert report["total_out_of_domain"] >= 2


def test_assign_splits_keeps_duplicate_groups_in_same_split():
    rows = []
    for index in range(70):
        row = raw_frame().iloc[0].to_dict()
        row[LABEL_COLUMN] = [
            "Insufficient_Weight",
            "Normal_Weight",
            "Overweight_Level_I",
            "Overweight_Level_II",
            "Obesity_Type_I",
            "Obesity_Type_II",
            "Obesity_Type_III",
        ][index % 7]
        row["Weight"] = 50.0 + index
        rows.append(row)

    duplicate = raw_frame().iloc[0].to_dict()
    duplicate[LABEL_COLUMN] = "Normal_Weight"
    duplicate["Weight"] = 60.0
    for _ in range(2):
        rows.append(dict(duplicate))

    duplicate2 = raw_frame().iloc[0].to_dict()
    duplicate2[LABEL_COLUMN] = "Obesity_Type_I"
    duplicate2["Weight"] = 90.0
    for _ in range(2):
        rows.append(dict(duplicate2))

    frame = encode_features(pd.DataFrame(rows))
    frame.insert(0, LABEL_COLUMN, [row[LABEL_COLUMN] for row in rows])
    result = assign_splits(frame, random_state=7)

    dup_key = list(FEATURE_NAMES) + [LABEL_COLUMN]
    duplicated = result.duplicated(subset=dup_key, keep=False)
    groups = result[duplicated].groupby(dup_key)
    assert groups.ngroups == 2
    for _, group in groups:
        assert group["split"].nunique() == 1
