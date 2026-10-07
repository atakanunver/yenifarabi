def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: gerçek modelle, yalnızca Bilgehan GPU1'de")
