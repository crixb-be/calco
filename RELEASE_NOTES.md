# DocForge Desktop v0.1.0

## Resumen

Suite documental privada y offline construida con Tauri v2, React 19 y Python 3.12 congelado con PyInstaller para Windows x64. La distribución incluye instalador NSIS y paquete portable sin requerir Python en el equipo final.

## Módulos incluidos

- **Conversor Universal:** Office a PDF mediante LibreOffice headless, PDF a imágenes con PyMuPDF a 150/300 DPI y transcodificación entre PNG, JPG y WebP.
- **Stirling-PDF Core:** Merge, Split, Compress, cifrado AES-256, desbloqueo y Organizador Visual interactivo con miniaturas a 72 DPI.
- **Docling Parser:** extracción estructurada hacia Markdown, JSON jerárquico, HTML y DocTags.

## Detalles técnicos

- Comunicación bidireccional streaming NDJSON entre React/Tauri y el sidecar Python.
- Historial local persistente limitado a los últimos 100 registros.
- Layout compacto estilo ILovePDF, optimizado para trabajar sin scroll forzado en 1080p.
- Notificaciones nativas de Windows al completar tareas en segundo plano.
- Sidecar autónomo con PyMuPDF y Pillow incluidos en el bundle.

## Artefactos y checksums

Los artefactos se generan con `scripts/package_release.ps1` y se verifican con `scripts/verify_distribution.ps1`.

| Archivo | Tamaño | SHA-256 |
|---|---:|---|
| `DocForge Desktop_0.1.0_x64-setup.exe` | 207,146,764 bytes | `d0a6c4d7eaea45ac5d18f1f83cec3bb5b28d523a4b8fb09f88bee9acf39eaf9a` |
| `DocForge-v0.1.0-Windows-x64-Portable.zip` | 210,610,474 bytes | `35b75fa11095ec0bce2ea81c3c82c6bcab72dc068820199053041cb45c9ce159` |

