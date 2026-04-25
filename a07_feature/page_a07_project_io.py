from __future__ import annotations

from pathlib import Path

from a07_feature import (
    load_a07_groups,
    load_locks,
    save_a07_groups,
    save_locks,
    save_mapping,
    save_project_state,
)
from a07_feature.page_paths import (
    copy_a07_source_to_workspace,
    default_a07_groups_path,
    default_a07_locks_path,
    default_a07_project_path,
    default_global_rulebook_path,
    get_a07_workspace_dir,
    resolve_autosave_mapping_path,
    resolve_rulebook_path,
    suggest_default_mapping_path,
    copy_rulebook_to_storage,
)

from .page_a07_env import filedialog, messagebox, session
from .page_a07_runtime_helpers import _clean_context_value
from src.pages.a07.backend.project_io import (
    autosave_mapping_file,
    build_project_state,
    mapping_load_path_decision,
    mapping_save_path_decision,
    save_mapping_file,
    save_workspace_state_files,
)


class A07PageProjectIoMixin:
    def _current_project_state(self) -> dict[str, object]:
        return build_project_state(
            basis_col=self.workspace.basis_col,
            selected_code=self._selected_control_code(),
            selected_group=self._selected_group_id(),
        )

    def _autosave_workspace_state(self) -> bool:
        client, year = self._session_context(session)
        client_s = _clean_context_value(client)
        year_s = _clean_context_value(year)
        if not client_s or not year_s:
            return False

        result = save_workspace_state_files(
            client=client_s,
            year=year_s,
            groups=self.workspace.groups,
            locks=self.workspace.locks,
            project_state=self._current_project_state(),
            default_groups_path=default_a07_groups_path,
            default_locks_path=default_a07_locks_path,
            default_project_path=default_a07_project_path,
            save_groups=save_a07_groups,
            save_locks_fn=save_locks,
            save_project_state_fn=save_project_state,
        )
        if result is None:
            return False
        self.groups_path = result.groups_path
        self.locks_path = result.locks_path
        self.project_path = result.project_path
        self._context_snapshot = self._current_context_snapshot(client_s, year_s)
        return True

    def _autosave_mapping(
        self,
        *,
        source: str = "manual",
        confidence: float | None = 1.0,
    ) -> bool:
        client, year = self._session_context(session)
        saved = autosave_mapping_file(
            explicit_mapping_path=self.mapping_path,
            a07_path=self.a07_path,
            client=client,
            year=year,
            mapping=self.workspace.mapping,
            source=source,
            confidence=confidence,
            resolve_path=resolve_autosave_mapping_path,
            save_mapping_fn=save_mapping,
        )
        if saved is None:
            return False
        self.mapping_path = Path(saved)
        self.mapping_path_var.set(f"Mapping: {self.mapping_path}")
        self._autosave_workspace_state()
        self._context_snapshot = self._current_context_snapshot(client, year)
        return True

    def _load_a07_clicked(self) -> None:
        client, year = self._session_context(session)
        initialdir = str(get_a07_workspace_dir(client, year))
        path = filedialog.askopenfilename(
            parent=self,
            title="Velg A07 JSON",
            initialdir=initialdir,
            filetypes=[("JSON", "*.json"), ("Alle filer", "*.*")],
        )
        if not path:
            return

        try:
            stored_path = copy_a07_source_to_workspace(path, client=client, year=year)
            self.workspace.source_a07_df = self._load_a07_source_cached(stored_path)
            self.workspace.a07_df = self.workspace.source_a07_df.copy()
            self.a07_path = Path(stored_path)
            self.a07_path_var.set(f"A07: {self.a07_path}")
            self._context_snapshot = self._current_context_snapshot(client, year)
            self._refresh_core(reason="load_a07")

            if stored_path != Path(path):
                self.status_var.set(
                    f"Lastet A07 fra {Path(path).name} og lagret kopi i klientmappen."
                )
            else:
                self.status_var.set(f"Lastet A07 fra {self.a07_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lese A07-filen:\n{exc}")

    def _load_mapping_clicked(self) -> None:
        client, year = self._session_context(session)
        decision = mapping_load_path_decision(
            a07_path=self.a07_path,
            client=client,
            year=year,
            suggest_path=suggest_default_mapping_path,
        )
        path = decision.path
        if decision.needs_dialog:
            path_str = filedialog.askopenfilename(
                parent=self,
                title="Velg mapping JSON",
                initialdir=str(path.parent),
                initialfile=path.name,
                filetypes=[("JSON", "*.json"), ("Alle filer", "*.*")],
            )
            if not path_str:
                return
            path = Path(path_str)

        try:
            self.workspace.mapping = self._load_mapping_file_cached(
                path,
                client=client,
                year=year,
            )
            self.mapping_path = Path(path)
            if client and year:
                try:
                    self.groups_path = default_a07_groups_path(client, year)
                    self.workspace.groups = load_a07_groups(self.groups_path)
                except Exception:
                    self.workspace.groups = {}
                try:
                    self.locks_path = default_a07_locks_path(client, year)
                    self.workspace.locks = load_locks(self.locks_path)
                except Exception:
                    self.workspace.locks = set()
            self.mapping_path_var.set(f"Mapping: {self.mapping_path}")
            self._refresh_core()
            self.status_var.set(f"Lastet mapping fra {self.mapping_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lese mapping-filen:\n{exc}")

    def _save_mapping_clicked(self) -> None:
        client, year = self._session_context(session)
        decision = mapping_save_path_decision(
            a07_path=self.a07_path,
            client=client,
            year=year,
            suggest_path=suggest_default_mapping_path,
        )
        out_path = decision.path
        if decision.needs_dialog:
            out_path_str = filedialog.asksaveasfilename(
                parent=self,
                title="Lagre mapping",
                defaultextension=".json",
                initialdir=str(out_path.parent),
                initialfile=out_path.name,
                filetypes=[("JSON", "*.json")],
            )
            if not out_path_str:
                return
            out_path = Path(out_path_str)

        try:
            saved = save_mapping_file(
                path=out_path,
                mapping=self.workspace.mapping,
                client=client,
                year=year,
                save_mapping_fn=save_mapping,
            )
            self.mapping_path = Path(saved)
            self.mapping_path_var.set(f"Mapping: {self.mapping_path}")
            self._autosave_workspace_state()
            self.status_var.set(f"Lagret mapping til {self.mapping_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lagre mapping:\n{exc}")

    def _on_basis_changed(self) -> None:
        basis = self._selected_basis()
        if basis == self.workspace.basis_col:
            return
        self.workspace.basis_col = basis
        self._refresh_core(focus_code=self._selected_control_code())
        self._autosave_workspace_state()
        self.status_var.set(f"A07 bruker nå basis {basis}.")

    def _load_rulebook_clicked(self) -> None:
        client, year = self._session_context(session)
        current_path = resolve_rulebook_path(client, year) or default_global_rulebook_path()
        path = filedialog.askopenfilename(
            parent=self,
            title="Velg A07 rulebook",
            initialdir=str(current_path.parent),
            initialfile=current_path.name,
            filetypes=[("JSON", "*.json"), ("Alle filer", "*.*")],
        )
        if not path:
            return

        try:
            stored_path = copy_rulebook_to_storage(path)
            self.rulebook_path = stored_path
            self.rulebook_path_var.set(f"Rulebook: {stored_path}")
            self._refresh_core(focus_code=self._selected_control_code())
            self.status_var.set(f"Rulebook lastet og lagret til {stored_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lese rulebook:\n{exc}")
