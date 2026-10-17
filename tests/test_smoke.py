# Keeps the pytest CI job green until real tests exist (pytest fails when it finds no tests).
def test_smoke():
    assert True
