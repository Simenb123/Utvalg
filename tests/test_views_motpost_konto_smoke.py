"""Smoketests for motpost GUI module.

We intentionally keep these tests UI-free (no Tk mainloop), but ensure that
key helpers imported into the module namespace exist. This catches refactor
regressions where callbacks refer to missing globals.
"""


def test_views_motpost_konto_has_required_helpers_imported():
    import views_motpost_konto as vm

    assert callable(vm.build_bilag_details)
    assert callable(vm.build_motkonto_combinations)
    assert callable(vm.build_motkonto_combinations_per_selected_account)
