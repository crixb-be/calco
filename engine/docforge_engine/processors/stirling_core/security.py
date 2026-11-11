from __future__ import annotations

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.paths import atomic_save, output_path, safe_stem
from .common import one_input, pikepdf_module


def _pymupdf_module():
    try:
        import pymupdf
        return pymupdf
    except ImportError as exc:
        raise EngineError("DEPENDENCY_MISSING", "PyMuPDF is required for PDF security actions", str(exc)) from exc


def _password_error(exc):
    pikepdf = pikepdf_module()
    if isinstance(exc, pikepdf.PasswordError):
        raise EngineError("WRONG_PASSWORD", "The supplied PDF password is incorrect") from exc
    raise exc


class PdfSecurityProcessor(BaseProcessor):
    engine_name = "stirling_core"

    @action("protect_pdf")
    def protect_pdf(self, task, reporter):
        """Encrypt a PDF with the native PyMuPDF AES-256 implementation."""
        pymupdf = _pymupdf_module()
        source = one_input(task)
        user_password = str(task.options.get("userPassword", task.options.get("password", "")))
        owner_password = str(task.options.get("ownerPassword", user_password))
        if not user_password:
            raise EngineError("INVALID_TASK", "protect_pdf.userPassword is required")
        if not owner_password:
            raise EngineError("INVALID_TASK", "protect_pdf.ownerPassword cannot be empty")

        try:
            document = pymupdf.open(str(source))
        except Exception as exc:
            raise EngineError("CONVERSION_FAILED", f"No se pudo abrir el PDF: {source.name}", str(exc)) from exc
        try:
            permissions = task.options.get("permissions")
            if not isinstance(permissions, int):
                permissions = (
                    pymupdf.PDF_PERM_ACCESSIBILITY
                    | pymupdf.PDF_PERM_COPY
                    | pymupdf.PDF_PERM_PRINT
                    | pymupdf.PDF_PERM_PRINT_HQ
                )
            out = output_path(task, safe_stem(source), "protect_pdf", ".pdf")
            atomic_save(
                out,
                lambda temp: document.save(
                    temp,
                    encryption=pymupdf.PDF_ENCRYPT_AES_256,
                    user_pw=user_password,
                    owner_pw=owner_password,
                    permissions=permissions,
                    garbage=4,
                    deflate=True,
                ),
            )
            reporter.report(100, "PDF protegido con AES-256")
            return [str(out)], {"encryption": "AES-256"}
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError("CONVERSION_FAILED", f"No se pudo proteger {source.name}", str(exc)) from exc
        finally:
            document.close()

    @action("unlock_pdf")
    def unlock_pdf(self, task, reporter):
        """Authenticate and write an unencrypted copy, clearing restrictions."""
        pymupdf = _pymupdf_module()
        source = one_input(task)
        password = str(task.options.get("password", ""))
        try:
            document = pymupdf.open(str(source))
        except Exception as exc:
            raise EngineError("CONVERSION_FAILED", f"No se pudo abrir el PDF: {source.name}", str(exc)) from exc
        try:
            if document.needs_pass:
                if not password or document.authenticate(password) <= 0:
                    raise EngineError("WRONG_PASSWORD", "La contraseña del PDF es incorrecta")
            out = output_path(task, safe_stem(source), "unlock_pdf", ".pdf")
            atomic_save(
                out,
                lambda temp: document.save(
                    temp,
                    encryption=pymupdf.PDF_ENCRYPT_NONE,
                    garbage=4,
                    clean=True,
                    deflate=True,
                ),
            )
            reporter.report(100, "PDF desbloqueado")
            return [str(out)], {"encrypted": False}
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError("CONVERSION_FAILED", f"No se pudo desbloquear {source.name}", str(exc)) from exc
        finally:
            document.close()

    @action()
    def sanitize(self, task, reporter):
        pikepdf = pikepdf_module()
        source = one_input(task)
        options = task.options
        try:
            pdf = pikepdf.Pdf.open(source, password=options.get("password", ""))
        except Exception as exc:
            _password_error(exc)
        try:
            def remove_key(mapping, key):
                if mapping is not None and key in mapping:
                    del mapping[key]

            if options.get("removeMetadata", True):
                with __import__("contextlib").suppress(Exception):
                    pdf.docinfo.clear()
                remove_key(pdf.Root, "/Metadata")
            if options.get("removeXmp", True):
                remove_key(pdf.Root, "/Metadata")
            if options.get("removeAttachments", True):
                names = pdf.Root.get("/Names")
                if names:
                    remove_key(names, "/EmbeddedFiles")
                for page in pdf.pages:
                    annots = page.get("/Annots")
                    if annots:
                        page["/Annots"] = pikepdf.Array([a for a in annots if a.get("/Subtype") != "/FileAttachment"])
            for page in pdf.pages:
                annots = page.get("/Annots")
                if not annots:
                    continue
                kept = []
                for annot in annots:
                    subtype = str(annot.get("/Subtype", ""))
                    action = annot.get("/A")
                    is_js = action is not None and str(action.get("/S", "")) in ("/JavaScript", "/Launch")
                    if options.get("removeLinks", True) and subtype == "/Link":
                        continue
                    if options.get("removeJs", True) and is_js:
                        continue
                    kept.append(annot)
                if kept:
                    page["/Annots"] = pikepdf.Array(kept)
                else:
                    remove_key(page, "/Annots")
            if options.get("removeJs", True):
                remove_key(pdf.Root, "/OpenAction")
                names = pdf.Root.get("/Names")
                if names:
                    remove_key(names, "/JavaScript")
            out = output_path(task, safe_stem(source), "sanitize", ".pdf")
            atomic_save(out, lambda temp: pdf.save(temp, linearize=False))
            reporter.report(100, "Sanitized PDF")
            return [str(out)], {}
        finally:
            pdf.close()

    @action()
    def protect(self, task, reporter):
        pikepdf = pikepdf_module()
        source = one_input(task)
        user = str(task.options.get("userPassword", ""))
        owner = str(task.options.get("ownerPassword", user))
        if not user:
            raise EngineError("INVALID_TASK", "protect.userPassword is required")
        try:
            pdf = pikepdf.Pdf.open(source)
        except Exception as exc:
            _password_error(exc)
        try:
            permissions = task.options.get("permissions", {}) or {}
            allow = pikepdf.Permissions(
                accessibility=bool(permissions.get("accessibility", True)),
                extract=bool(permissions.get("extract", True)),
                modify_annotation=bool(permissions.get("modifyAnnotation", False)),
                modify_form=bool(permissions.get("modifyForm", False)),
                modify_other=bool(permissions.get("modifyOther", False)),
                print_lowres=bool(permissions.get("print", True)),
                print_highres=bool(permissions.get("printHighResolution", True)),
            )
            encryption = pikepdf.Encryption(user=user, owner=owner, R=6, allow=allow)
            out = output_path(task, safe_stem(source), "protect", ".pdf")
            atomic_save(out, lambda temp: pdf.save(temp, encryption=encryption))
            reporter.report(100, "Protected PDF")
            return [str(out)], {"encryption": "AES-256"}
        finally:
            pdf.close()

    @action()
    def unprotect(self, task, reporter):
        pikepdf = pikepdf_module()
        source = one_input(task)
        password = str(task.options.get("password", ""))
        try:
            pdf = pikepdf.Pdf.open(source, password=password)
        except Exception as exc:
            _password_error(exc)
        try:
            out = output_path(task, safe_stem(source), "unprotect", ".pdf")
            atomic_save(out, lambda temp: pdf.save(temp))
            reporter.report(100, "Removed PDF encryption")
            return [str(out)], {}
        finally:
            pdf.close()
