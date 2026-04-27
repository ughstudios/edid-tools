import unittest

from edid.windows_display import (
    DisplayInstance,
    WindowsDisplayError,
    _delete_value,
    _guard_active_edid_instance,
)


class WindowsDisplaySafetyTests(unittest.TestCase):
    def test_active_edid_instance_cannot_be_deleted(self) -> None:
        display = DisplayInstance(
            device_id="CSW150F",
            instance_id="5&active&0&UID4355",
            device_desc="Integrated Monitor",
            active_data=object(),  # type: ignore[arg-type]
            override_data=None,
        )

        with self.assertRaisesRegex(WindowsDisplayError, "active display"):
            _guard_active_edid_instance(display, action="delete monitor registry instance")

    def test_inactive_instance_can_pass_delete_guard(self) -> None:
        display = DisplayInstance(
            device_id="CSW150F",
            instance_id="5&inactive&0&UID4355",
            device_desc="Integrated Monitor",
            active_data=None,
            override_data=None,
        )

        _guard_active_edid_instance(display, action="delete monitor registry instance")

    def test_delete_value_refuses_edid(self) -> None:
        with self.assertRaisesRegex(WindowsDisplayError, "active EDID"):
            _delete_value(object(), "EDID")


if __name__ == "__main__":
    unittest.main()
