<p align="center">
  <img src="refspider_icono_limpio.png" alt="Logo de Refspider" width="128">
</p>

# Refspider

## Descargar la app

No hace falta instalar Python. Descarga la versión para tu sistema desde la última release:

- **macOS:** [Refspider-macos.zip](https://github.com/DotStefano/Refspider/releases/latest/download/Refspider-macos.zip). La primera vez, haz clic derecho sobre la app y elige **Abrir**.
- **Windows 11:** [Refspider-windows.zip](https://github.com/DotStefano/Refspider/releases/latest/download/Refspider-windows.zip). Si aparece SmartScreen, pulsa **Más información** y luego **Ejecutar de todas formas**.
- **Linux:** [Refspider-linux.tar.gz](https://github.com/DotStefano/Refspider/releases/latest/download/Refspider-linux.tar.gz). Descomprime, dale permisos con `chmod +x Refspider` y ejecútalo.

## Ejecutar desde el código

Añade enlaces clicables a las citas, figuras y tablas de un PDF académico.

Selecciona el PDF, indica el formato de las citas (corchetes, paréntesis o superíndice) y las páginas de la bibliografía. Refspider crea una copia del documento con los enlaces: cada cita lleva a su entrada en la bibliografía, y cada mención de figura o tabla lleva a su leyenda.

## Uso

```bash
pip install -r requirements.txt
python3 refspider.py
```

## Opciones

- **Formato de las citas:** corchetes `[1]`, paréntesis `(1)` o superíndice.
- **Figuras y tablas:** enlaza las menciones «Figura n» y «Tabla n» con sus leyendas.
- **Bibliografía:** rango de páginas donde está la lista de referencias.
- **Nombre de salida:** el PDF nuevo se guarda junto al original.

## Limitaciones

- Las leyendas de figuras y tablas deben empezar por «Figura n.» o «Tabla n:».
- Los años entre paréntesis, como `(2021)`, se detectan como citas en el modo paréntesis.
- La detección de superíndices depende de cómo se generó el PDF.

## Licencia

MIT. Consulta el archivo [LICENSE](LICENSE).
