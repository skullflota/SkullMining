# Skull Mining

Herramienta de la **flota Skull** para encontrar los mejores sitios de minería en superficie con el Rhino en *Elite Dangerous*.

Tiene dos partes:
- **Plugin de EDMC** (`SkullMining/`): cada miembro lo instala. Graba automáticamente sus sesiones de minería con el Rhino (plataformas, distancias, recorrido, toneladas) y las envía a la hoja de la flota.
- **Hoja de Google** (`hoja/Code.gs`): recibe los datos de todos y los agrupa por **sitio**, es decir, una zona de un solo mineral de unos 50 m. De cada sitio muestra el máximo de plataformas conseguido (con una separación mínima de 47 m entre ellas), el valor por vuelta, las distancias y el terreno.

## Ranking de sitios

La web **https://skullflota.github.io/SkullMining/** muestra los sitios ordenados por valor por vuelta, con filtros por mineral, plataformas y terreno. El código está en `docs/`, y la URL de la hoja se configura en `docs/config.js`.

## Instalar el plugin (miembros)

1. Descarga el zip de la última versión en **Releases**.
2. En EDMC: **Archivo → Ajustes → Plugins → Abrir**. Descomprime ahí la carpeta `SkullMining` y reinicia EDMC.
3. En **Ajustes → Skull Mining**, pega la **URL** y la **clave de la flota**. Te las dan los mandos de la flota; no las publiques aquí.

Para actualizar, repite el paso 2 sustituyendo la carpeta. No borres `pending.json`: guarda lo que falte por enviar.

Todos los detalles técnicos (qué se envía, cómo se calcula, montaje de la hoja) están en [LEEME.md](LEEME.md).

## Pruebas

```
python tests/test_simulado.py
python tests/test_journal_real.py
```
