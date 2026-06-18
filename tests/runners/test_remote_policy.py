import pytest
import sys; sys.path.insert(0, ".")
from backend.runners.remote_policy import RemotePolicyRunner

def test_instantiation():
    r = RemotePolicyRunner({"endpoint": "http://localhost:7860"})
    assert r.endpoint == "http://localhost:7860"

@pytest.mark.asyncio
async def test_run_raises_not_implemented():
    r = RemotePolicyRunner({"endpoint": "http://localhost:7860"})
    with pytest.raises(NotImplementedError):
        await r.run({}, seed=0)
