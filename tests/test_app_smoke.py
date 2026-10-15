import unittest


try:
    import flet as ft

    from c_deck import app
except ModuleNotFoundError:
    ft = None
    app = None


@unittest.skipIf(ft is None, "Flet is not installed in this Python environment.")
class AppSmokeTest(unittest.TestCase):
    def test_app_module_exposes_main(self):
        self.assertTrue(callable(app.main))

    def test_flet_controls_used_by_app_are_compatible(self):
        ft.Dropdown(
            label="Catégorie",
            dense=True,
            border_radius=8,
            editable=True,
            enable_filter=True,
            enable_search=True,
        )
        ft.FilePicker()
        ft.TextField(prefix_icon=ft.Icons.SEARCH)


if __name__ == "__main__":
    unittest.main()
