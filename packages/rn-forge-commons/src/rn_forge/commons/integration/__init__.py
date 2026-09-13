"""Protocols for the systems an application talks to, and the resilience helpers.

Messaging, object storage and secret storage are defined as protocols with
in-memory implementations: the protocol lives in the lowest package that can
hold it, and the adapter lives in the package that owns the technology.
:mod:`~rn_forge.commons.integration.resilience` needs the ``resilience`` extra;
:mod:`~rn_forge.commons.integration.auth` (token verification) needs the ``auth``
extra.
"""
