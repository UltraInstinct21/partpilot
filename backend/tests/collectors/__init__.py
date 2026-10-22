"""Tests of the PartPilot collection layer (owned by agent A).

Every test is hermetic: no test ever touches the network. HTTP is mocked with
``respx`` and the recorded fixtures in ``contracts/fixtures`` are the payloads
that the mocks return.
"""
