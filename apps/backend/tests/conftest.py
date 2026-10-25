# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from studio_backend.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
