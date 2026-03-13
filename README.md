# OPEN-RUBRICA

Herramienta para firmar PDFs digitalmente con **DNIe español** (o certificado `.p12`), mediante interfaz web offline para posicionar visualmente la firma en cada página.

**Sin Java. Sin instaladores. Sin complicaciones.**

> Con Java y AutoFirma la experiencia en Linux es... una aventura. Este proyecto nació exactamente de esa frustración.

Construido con Python, [pyhanko](https://pyhanko.readthedocs.io) y [pymupdf](https://pymupdf.readthedocs.io).  
Desarrollado con la asistencia de [Claude Sonnet](https://claude.ai) (Anthropic).

---

## Características

- 🔏 Firma digital PAdES válida bajo el marco **eIDAS** — legalmente reconocida en España
- 📄 Firma **múltiples páginas** de un PDF, o todas a la vez con un solo clic
- 🖱️ **Posicionamiento visual** de la firma arrastrando el ratón sobre el PDF
- ✍️ Posibilidad de añadir una **rúbrica dibujada a mano** (con fondo transparente)
- ☕ **Sin Java** — porque ya sufrimos bastante con AutoFirma en Linux
- 🌐 Interfaz web **offline** — sin CDN, sin dependencias de red
- 🔗 Firmas incrementales: cada nueva firma preserva las anteriores

---

## Flujo de uso

```
python main.py
     │
     ├─▶ Servidor HTTP local (localhost:8765)
     │        │
     │        ├─▶ [1] Cargar PDF          ← drag & drop en el navegador
     │        ├─▶ [2] Posicionar firma    ← clic + arrastre en cada página
     │        ├─▶ [3] Rúbrica (opcional)  ← dibujo a mano en canvas
     │        ├─▶ [4] Auth DNIe           ← selección de certificado + PIN
     │        └─▶ [5] Descarga            ← nombre_firmado.pdf
     │
     └─▶ utils.py
              ├─▶ pymupdf   → renderiza páginas como imágenes (offline)
              ├─▶ PKCS#11   → comunica con el DNIe vía opensc
              └─▶ pyhanko   → firma incremental PAdES en cada página
```

---

## Requisitos previos

### Hardware
- DNIe español (versión 3.0 o superior, con chip activo)
- Lector de tarjeta compatible con el estándar PC/SC (la mayoría de lectores USB lo son)

---

### 1 · Certificados raíz del DNIe y la FNMT

El sistema necesita confiar en la cadena de certificados del DNIe y de la FNMT.

La FNMT ofrece descarga oficial en su web, aunque solo documenta Debian y Fedora.  
En Manjaro/Arch el camino más directo es el AUR:

👉 [https://www.sede.fnmt.gob.es/descargas/descarga-software](https://www.sede.fnmt.gob.es/descargas/descarga-software)

**Manjaro / Arch — vía AUR:**

```bash
pamac build ca-certificates-dnie
pamac build ca-certificates-fnmt
```

> ⚠️ Estos paquetes son conocidos por dar problemas: la FNMT actualiza sus certificados sin avisar y los checksums del PKGBUILD quedan desfasados. Si `pamac` falla con errores de validación, prueba con `makepkg` directamente:
>
> ```bash
> git clone https://aur.archlinux.org/ca-certificates-dnie.git
> cd ca-certificates-dnie && makepkg -si
> ```
>
> Si el error es de SSL al descargar, es un problema conocido con la cadena de la FNMT. Los comentarios del AUR tienen siempre el workaround más actualizado:
> - [ca-certificates-dnie en AUR](https://aur.archlinux.org/packages/ca-certificates-dnie)
> - [ca-certificates-fnmt en AUR](https://aur.archlinux.org/packages/ca-certificates-fnmt)

**Otras distribuciones — instalación manual:**

Descarga los `.cer` desde la web de la FNMT e instálalos en el almacén del sistema:

```bash
# Debian / Ubuntu
sudo cp AC_Raiz_FNMT-RCM.cer /usr/local/share/ca-certificates/
sudo update-ca-certificates

# Fedora / RHEL
sudo cp AC_Raiz_FNMT-RCM.cer /etc/pki/ca-trust/source/anchors/
sudo update-ca-trust
```

---

### 2 · Drivers del lector

**Manjaro / Arch:**

```bash
# Drivers PKCS#11 para tarjetas inteligentes y demonio PC/SC
pamac install opensc ccid

# Activar el demonio PC/SC (imprescindible para que el lector funcione)
sudo systemctl enable --now pcsclite
```

**Debian / Ubuntu:**

```bash
sudo apt install opensc ccid pcscd
sudo systemctl enable --now pcscd
```

**Fedora:**

```bash
sudo dnf install opensc ccid pcsc-lite
sudo systemctl enable --now pcscd
```

Verifica que el DNIe se detecta:

```bash
opensc-tool --list-readers
# Con el DNIe insertado:
pkcs11-tool --module /usr/lib/opensc-pkcs11.so --list-objects
```

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/tuusuario/open-rubrica
cd open-rubrica

# 2. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias Python
pip install -r requirements.txt

# 4. Ejecutar — el navegador se abre automáticamente
python main.py
```

Listo. Se abrirá el navegador en `http://localhost:8765` y podrás arrastrar cualquier PDF para firmarlo.

---

## Opciones de línea de comandos

```bash
python main.py                          # DNIe (por defecto)
python main.py --p12 cert.p12           # certificado .p12 / .pfx
python main.py --puerto 9000            # puerto distinto al predeterminado
python main.py --pkcs11-lib /ruta/lib   # librería PKCS#11 alternativa
python main.py --nombre "Ana García"    # nombre si no se lee del certificado
python main.py --font-size 8            # tamaño del texto de firma
```

### Librería PKCS#11 según distribución

| Distribución | Ruta |
|---|---|
| Arch / Manjaro | `/usr/lib/opensc-pkcs11.so` |
| Ubuntu / Debian | `/usr/lib/x86_64-linux-gnu/opensc-pkcs11.so` |
| Fedora | `/usr/lib64/opensc-pkcs11.so` |

---

## Dependencias Python

| Paquete | Uso |
|---|---|
| `pyhanko` | Motor de firma PDF/PAdES |
| `pyhanko-certvalidator` | Validación de cadena de certificados |
| `python-pkcs11` | Comunicación con el DNIe vía PKCS#11 |
| `asn1crypto` | Extracción del nombre del firmante del certificado X.509 |
| `Pillow` | Procesado de la imagen de rúbrica |
| `pymupdf` | Renderizado offline de páginas PDF como imágenes |

> `python-pkcs11` requiere compilación C. En Manjaro/Arch: `pamac install base-devel` si no lo tienes ya.

---

## Seguridad

- El servidor HTTP escucha **únicamente en `localhost`** — ningún otro equipo de la red puede acceder.
- El PDF nunca sale del equipo.
- El PIN del DNIe se usa directamente para abrir la sesión PKCS#11. No se almacena ni se registra.
- La firma generada es **PAdES**, válida legalmente en España bajo el marco **eIDAS**.

---

## Licencia

[GNU General Public License v3.0](LICENSE)

Este software es libre: puedes redistribuirlo y/o modificarlo bajo los términos de la GNU GPL v3 o posterior.
