# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

"""Peer state unit tests."""

import json
from unittest import TestCase

from state import State, requires_state, requires_state_setter


class TestState(TestCase):
    """Unit tests for state.

    Attrs:
        maxDiff: Specifies max difference shown by failed tests.
    """

    maxDiff = None

    def test_get(self):
        """It is possible to retrieve attributes from the state."""
        state = make_state({"foo": json.dumps("bar")})
        self.assertEqual(state.foo, "bar")
        self.assertIsNone(state.bad)

    def test_set(self):
        """It is possible to set attributes in the state."""
        data = {"foo": json.dumps("bar")}
        state = make_state(data)
        state.foo = 42
        state.list = [1, 2, 3]
        self.assertEqual(state.foo, 42)
        self.assertEqual(state.list, [1, 2, 3])
        self.assertEqual(data, {"foo": "42", "list": "[1, 2, 3]"})

    def test_del(self):
        """It is possible to unset attributes in the state."""
        data = {"foo": json.dumps("bar"), "answer": json.dumps(42)}
        state = make_state(data)
        del state.foo
        self.assertIsNone(state.foo)
        self.assertEqual(data, {"answer": "42"})
        # Deleting a name that is not set does not error.
        del state.foo

    def test_is_ready(self):
        """The state is not ready when it is not possible to get relations."""
        state = make_state({})
        self.assertTrue(state.is_ready())

        state = State("myapp", lambda: None)
        self.assertFalse(state.is_ready())

    def test_requires_state_decorator(self):
        """Test `requires_state` decorator"""
        with self.subTest("ready"):
            stateful = Stateful(state_ready=True, is_leader=False)
            self.assertTrue(stateful._state.is_ready())
            event = MockEvent()

            value = stateful.method_with_requires_state(event)

            self.assertTrue(value)
            self.assertFalse(event.defer_called)

        with self.subTest("not ready"):
            stateful = Stateful(state_ready=False, is_leader=False)
            self.assertFalse(stateful._state.is_ready())
            event = MockEvent()

            value = stateful.method_with_requires_state(event)

            self.assertIsNone(value)
            self.assertTrue(event.defer_called)

    def test_requires_state_setter_decorator(self):
        """Test `requires_state_setter` decorator"""
        with self.subTest("ready, leader"):
            stateful = Stateful(state_ready=True, is_leader=True)
            self.assertTrue(stateful._state.is_ready())
            event = MockEvent()

            value = stateful.method_with_requires_state_setter(event)

            self.assertTrue(value)
            self.assertTrue(stateful.unit.is_leader_called)

        with self.subTest("not ready, leader"):
            stateful = Stateful(state_ready=False, is_leader=True)
            self.assertFalse(stateful._state.is_ready())
            event = MockEvent()

            value = stateful.method_with_requires_state_setter(event)

            self.assertIsNone(value)
            self.assertTrue(stateful.unit.is_leader_called)

        with self.subTest("ready, non-leader"):
            stateful = Stateful(state_ready=True, is_leader=False)
            self.assertTrue(stateful._state.is_ready())
            event = MockEvent()

            value = stateful.method_with_requires_state_setter(event)

            self.assertIsNone(value)
            self.assertTrue(stateful.unit.is_leader_called)

        with self.subTest("not ready, non-leader"):
            stateful = Stateful(state_ready=False, is_leader=False)
            self.assertFalse(stateful._state.is_ready())
            event = MockEvent()

            value = stateful.method_with_requires_state_setter(event)

            self.assertIsNone(value)
            self.assertTrue(stateful.unit.is_leader_called)


class Stateful:
    """Test class with an _state property"""
    def __init__(self, state_ready: bool, is_leader: bool) -> None:
        self._state = make_state({}, ready=state_ready)
        self.unit = MockUnit(is_leader)

    @requires_state
    def method_with_requires_state(self, event):
        """Mock to test `requires_state`"""
        return True

    @requires_state_setter
    def method_with_requires_state_setter(self, event):
        """Mock to test `requires_state_setter`"""
        return True


class MockEvent:
    """A mock event"""
    defer_called = False

    def defer(self):
        """Mock defer"""
        self.defer_called = True


class MockUnit:
    """A mock unit"""
    is_leader_called = False

    def __init__(self, is_leader: bool) -> None:
        self._is_leader = is_leader

    def is_leader(self):
        """Returns True if unit is leader"""
        self.is_leader_called = True
        return self._is_leader


def make_state(data, ready: bool = True):
    """Create state object.

    Args:
        data: Data to be included in state.

    Returns:
        State object with data.
    """
    app = "myapp"
    rel = type("Rel", (), {"data": {app: data}})() if ready else None
    return State(app, lambda: rel)
