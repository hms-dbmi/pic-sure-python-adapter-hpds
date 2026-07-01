from picsure import genomicConsequences


def test_returns_dataframe_with_expected_columns():
    df = genomicConsequences()
    assert list(df.columns) == ["severity", "consequence"]


def test_row_count_matches_vocabulary():
    # 6 high + 4 medium + 8 low
    assert len(genomicConsequences()) == 18


def test_severity_order_preserved():
    df = genomicConsequences()
    assert df["severity"].iloc[0] == "High Severity"
    assert df["severity"].iloc[-1] == "Low Severity"


def test_known_consequence_maps_to_severity():
    df = genomicConsequences()
    row = df[df["consequence"] == "stop_gained"]
    assert row["severity"].iloc[0] == "High Severity"
