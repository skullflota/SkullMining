/**
 * Skull Mining - receptor de datos de la flota (Google Apps Script).
 *
 * Instalación (una sola vez, la hace el administrador):
 *   1. Crear una Hoja de cálculo de Google nueva → Extensiones → Apps Script.
 *   2. Pegar este archivo como Code.gs y guardar.
 *   3. Ejecutar la función `setup` (pedirá permisos). Crea las pestañas y una clave.
 *      La clave aparece en el registro de ejecución y en Configuración del proyecto →
 *      Propiedades del script → FLEET_TOKEN.
 *   4. Implementar → Nueva implementación → Aplicación web.
 *      Ejecutar como: Yo. Quién tiene acceso: Cualquier usuario.
 *   5. Pasar a la flota la URL de la aplicación web y la clave.
 */

var SITE_MATCH_M = 150;    // un depósito (un solo mineral) mide hasta ~100 m de radio; 2 taladros a 103 m en la misma mancha (28-sep)
var ZONE_RADIUS_M = 10000; // zonas de varios km (más grandes en planetas grandes); se asigna la más cercana
var TRACK_CHUNK = 45000;   // límite práctico por celda
var SCHEMA_VERSION = '12';  // sube cuando se añaden columnas o pestañas
var WEB_URL = 'https://skullflota.github.io/SkullMining/';
// Alto/Medio/Bajo es la DENSIDAD del sitio (fija, la genera el juego). Agotado es aparte:
// el desgaste lo comparten todos los jugadores y un sitio agotado no se regenera.
var STATE_LABELS = { alto: 'Alta', medio: 'Media', bajo: 'Baja', agotado: 'Agotado',
                     cant_alta: 'Cantidad alta', cant_media: 'Cantidad media', cant_baja: 'Cantidad baja' };
var OLD_DENSITY = { 'Alto': 'Alta', 'Medio': 'Media', 'Bajo': 'Baja' };

var HEADERS = {
  'Sitios': ['SiteID', 'Sistema', 'Cuerpo', 'Mineral', 'Nombre interno', 'Precio (Cr)', 'Lat', 'Lon',
             'Máx taladros', 'Dist. mín entre taladros (m)', 'Extensión (m)', 'T/recogida',
             'Valor por vuelta (Cr)', 'Visitas', 'Recogidas', 'Toneladas totales', 'Sitio más cercano (m)',
             'Mismo mineral más cercano (m)', 'Terreno zona', 'Vel. efectiva zona (m/s)', 'Señal zona',
             'Sitios minería en cuerpo', 'Tipo planeta', 'Gravedad (g)', 'Temp (K)', 'Última visita', 'Último CMDR',
             'Zona', 'Densidad', 'Densidad fecha', 'Densidad CMDR', 'Agotado', 'Agotado CMDR',
             'Cantidad', 'Cantidad fecha', 'Cantidad CMDR', 'Cantidad t flota', 'Taladros marcados',
             'Agotado desde', 'Regenerado', 'Regenerado CMDR', 'Creado', 'Cr/h', 'Descubierto por'],
  'Visitas': ['SessionID', 'SiteID', 'Fecha', 'CMDR', 'Mineral', 'Taladros', 'Dist. mín entre taladros (m)',
              'Extensión (m)', 'Recogidas', 'Toneladas', 'T/recogida', 'Terreno zona', 'Vel. efectiva zona (m/s)',
              'Zona'],
  'Sesiones': ['SessionID', 'Sitios', 'Recibido', 'CMDR', 'Sistema', 'Cuerpo', 'Inicio', 'Fin', 'Duración (min)',
               'Taladros', 'Recogidas', 'T/recogida', 'Ciclo recogida (min)', 'Señal zona',
               'Sitios minería en cuerpo', 'Materiales', 'Cargas a nave (t)', 'Toneladas', 'Valor estimado (Cr)',
               'Cr/h', 'Ruta recogida (m)', 'Vel. efectiva (m/s)', 'Vel. en movimiento (m/s)', 'Sinuosidad',
               'Terreno', 'Recorrido (m)', 'Minerales', 'Tipo planeta', 'Gravedad (g)', 'Temp (K)', 'Radio (m)',
               'Vehículo', 'Motivo cierre', 'Eventos desconocidos', 'Versión plugin', 'Zonas'],
  'Taladros': ['SessionID', 'SiteID', 'Nº', 'Lat', 'Lon', 'Mineral', 'Toneladas', 'Recogidas', 'T/recogida',
                  'Primera', 'Última'],
  'Tramos': ['SessionID', 'De', 'A', 'Línea recta (m)', 'Recorrido (m)', 'Tiempo (s)',
             'Vel. efectiva (m/s)', 'Sinuosidad'],
  'Recorridos': ['SessionID', 'Parte', 'Datos (t,lat,lon,alt;...)'],
  // Datos en bruto de cada tonelada (plugin 0.5.0+). Las partes se concatenan en orden.
  'Recogidas': ['SessionID', 'Inicio (epoch s)', 'Parte', 'Datos (décimas de s,tipo,lat,lon,zona;...)'],
  'Cuerpos': ['Sistema', 'Cuerpo', 'Tipo planeta', 'Gravedad (g)', 'Temp (K)', 'Radio (m)', 'Atmósfera',
              'Distancia (ls)', 'Sitios de minería', 'Señales', 'Actualizado', 'CMDR', 'Vulcanismo'],
  'Ventas': ['Fecha', 'CMDR', 'Tipo', 'Nombre', 'Cantidad', 'Precio venta', 'Total', 'Sistema', 'MarketID'],
  'Eventos': ['Fecha', 'CMDR', 'Evento', 'Sistema', 'Cuerpo', 'Lat', 'Lon', 'JSON'],
  'Precios': ['Tipo (interno)', 'Nombre ES', 'Nombre EN', 'Precio medio (Cr)', 'Interno verificado'],
  // Zonas de minería (señales "Planetary Mining Location Signal (N)"). La columna de minerales
  // se rellena a mano: el juego solo muestra esa lista en pantalla al fijar la zona.
  'Zonas': ['Sistema', 'Cuerpo', 'Zona', 'Lat', 'Lon', 'Minerales (anotar a mano)', 'Minerales confirmados',
            'Sitios', 'Mejor valor por vuelta (Cr)', 'Actualizado'],
  'Estados': ['Fecha', 'CMDR', 'Sistema', 'Cuerpo', 'Zona', 'Lat', 'Lon', 'Mineral', 'Estado', 'SiteID',
              'T sesión', 'T flota al marcar'],
  // Un sitio agotado que alguien vuelve a marcar con cantidad (alta, media o baja) cuenta como regenerado.
  // El tiempo real de regeneración está entre "Días mín" (hasta la última vez que se vio agotado) y
  // "Días máx" (hasta que se vio regenerado), porque solo lo sabemos cuando alguien lo marca.
  'Regeneraciones': ['SiteID', 'Sistema', 'Cuerpo', 'Mineral', 'Agotado desde', 'Visto agotado por última vez',
                     'Regenerado', 'CMDR', 'Días mín', 'Días máx']
};
var REGEN_MIN_H = 6; // una cantidad marcada a menos de 6 h de un "Agotado" se toma por una corrección, no por una regeneración

var PRICE_SEED = [
  ['monazite', 'Monacita', 'Monazite', 270000], ['alexandrite', 'Alejandrita', 'Alexandrite', 229000],
  ['grandidierite', 'Grandidierita', 'Grandidierite', 213000], ['iridium', 'Iridio', 'Iridium', 212000],
  ['periclasedunite', 'Dunita de periclasa', 'Periclase Dunite', 206000], ['thortveitite', 'Thortveitita', 'Thortveitite', 206000],
  ['serendibite', 'Serendibita', 'Serendibite', 188000], ['rhodplumsite', 'Rhodplumsita', 'Rhodplumsite', 187000],
  ['diamond', 'Diamante', 'Diamond', 136000], ['lowtemperaturediamond', 'Diamantes de baja temp.', 'Low Temperature Diamonds', 130000],
  ['sapphire', 'Zafiro', 'Sapphire', 129000], ['ruby', 'Rubí', 'Ruby', 111000], ['helium', 'Helio', 'Helium', 104000],
  ['helium3', 'Helio-3', 'Helium-3', 97000], ['bastnasite', 'Bastnasita', 'Bastnasite', 80000],
  ['platinum', 'Platino', 'Platinum', 71000], ['osmium', 'Osmio', 'Osmium', 56000], ['tritium', 'Tritio', 'Tritium', 53000],
  ['palladium', 'Paladio', 'Palladium', 52000], ['gold', 'Oro', 'Gold', 47000],
  ['quartzpyroxenite', 'Piroxenita de cuarzo', 'Quartz Pyroxenite', 47000], ['jadeite', 'Jadeíta', 'Jadeite', 42000],
  ['deuterium', 'Deuterio', 'Deuterium', 41000], ['magnesite', 'Magnesita', 'Magnesite', 38000],
  ['silver', 'Plata', 'Silver', 37000], ['olivine', 'Olivino', 'Olivine', 32000], ['samarium', 'Samario', 'Samarium', 28000],
  ['tantalum', 'Tantalio', 'Tantalum', 14000], ['thorium', 'Torio', 'Thorium', 12000], ['uranium', 'Uranio', 'Uranium', 7000],
  ['titanium', 'Titanio', 'Titanium', 4000], ['uraninite', 'Uraninita', 'Uraninite', 3000],
  ['methanolmonohydratecrystals', 'Cristales de metanol', 'Methanol Monohydrate Crystals', 2000],
  ['hematite', 'Hematita', 'Hematite', 2000], ['lithium', 'Litio', 'Lithium', 2000], ['copper', 'Cobre', 'Copper', 700],
  ['water', 'Agua', 'Water', 496]
];

// ------------------------------------------------------------------- instalación
function setup() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  ensureSchema_(true);
  var precios = ss.getSheetByName('Precios');
  if (precios.getLastRow() === 1) {
    precios.getRange(2, 1, PRICE_SEED.length, 5).setValues(PRICE_SEED.map(function (r) { return r.concat(['no']); }));
  }
  var def = ss.getSheetByName('Hoja 1') || ss.getSheetByName('Sheet1');
  if (def && def.getLastRow() === 0 && ss.getSheets().length > 1) ss.deleteSheet(def);

  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty('FLEET_TOKEN')) {
    props.setProperty('FLEET_TOKEN', Utilities.getUuid().replace(/-/g, '').slice(0, 16));
  }
  Logger.log('Clave de la flota: ' + props.getProperty('FLEET_TOKEN'));
  if (!props.getProperty('DISCORD_MODE')) props.setProperty('DISCORD_MODE', 'novedades');
}

// Crea las pestañas que falten y añade al final las columnas nuevas de cada versión.
function ensureSchema_(force) {
  var props = PropertiesService.getScriptProperties();
  if (!force && props.getProperty('SCHEMA_VERSION') === SCHEMA_VERSION) return;
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  renameToTaladros_(ss);
  var migrateStates = renameStateColumns_(ss);
  Object.keys(HEADERS).forEach(function (name) {
    var want = HEADERS[name];
    var sh = ss.getSheetByName(name) || ss.insertSheet(name);
    if (sh.getLastRow() === 0) {
      sh.appendRow(want);
      sh.setFrozenRows(1);
      sh.getRange(1, 1, 1, want.length).setFontWeight('bold').setBackground('#fff2cc');
      return;
    }
    var have = sh.getRange(1, 1, 1, Math.max(sh.getLastColumn(), 1)).getValues()[0];
    // Añadir al final las columnas que falten, por nombre (no por número: la hoja puede tener columnas de más)
    var extra = want.filter(function (h) { return have.indexOf(h) < 0; });
    if (extra.length) {
      var last = have.length;
      while (last > 0 && have[last - 1] === '') last--;
      sh.getRange(1, last + 1, 1, extra.length).setValues([extra]).setFontWeight('bold').setBackground('#fff2cc');
    }
  });
  if (migrateStates) recomputeAllStates_();
  props.setProperty('SCHEMA_VERSION', SCHEMA_VERSION);
}

// v7: "plataforma" pasa a llamarse "taladro" (pestaña y cabeceras)
function renameToTaladros_(ss) {
  var old = ss.getSheetByName('Plataformas');
  if (old && !ss.getSheetByName('Taladros')) old.setName('Taladros');
  ['Sitios', 'Visitas', 'Sesiones'].forEach(function (name) {
    var sh = ss.getSheetByName(name);
    if (!sh || sh.getLastRow() === 0) return;
    var have = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
    have.forEach(function (h, i) {
      var n = String(h).replace(/Plataformas/g, 'Taladros').replace(/plataformas/g, 'taladros');
      if (n !== h) sh.getRange(1, i + 1).setValue(n);
    });
  });
}

// v5: la columna "Estado" pasa a llamarse "Densidad" y el agotado va en columnas aparte.
function renameStateColumns_(ss) {
  var sh = ss.getSheetByName('Sitios');
  if (!sh || sh.getLastRow() === 0) return false;
  var have = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  var map = { 'Estado': 'Densidad', 'Estado fecha': 'Densidad fecha', 'Estado CMDR': 'Densidad CMDR' };
  var changed = false;
  have.forEach(function (h, i) {
    if (map[h]) { sh.getRange(1, i + 1).setValue(map[h]); changed = true; }
  });
  return changed;
}

// ---------------------------------------------------------------------- entrada
function doPost(e) {
  var body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({ ok: false, error: 'json' });
  }
  var token = PropertiesService.getScriptProperties().getProperty('FLEET_TOKEN');
  if (!body || body.token !== token) return json_({ ok: false, error: 'token' });

  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    ensureSchema_(false);
    var d = body.data || {};
    switch (body.kind) {
      case 'session': handleSession_(d); break;
      case 'sale': handleSale_(d); break;
      case 'body': handleBody_(d); break;
      case 'event': handleEvent_(d); break;
      case 'state': handleState_(d); break;
      case 'mark': handleMark_(d); break;
      default: return json_({ ok: false, error: 'kind' });
    }
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
  maybePostVacuum_();
  return json_({ ok: true });
}

// Lectura de sitios para el futuro visor: ?token=...&sheet=Sitios
function doGet(e) {
  var p = (e && e.parameter) || {};
  // Lectura para la web: solo miembros de la flota (CMDR de la lista + clave de la flota)
  if (p.view === 'ranking' || p.view === 'sell') {
    var acc = checkAccess_(p.cmdr, p.key);
    if (!acc.ok) return jsonp_(acc, p.callback);
    if (p.view === 'sell') return jsonp_(sellPlaces_(p.mineral, p.system), p.callback);
    ensureSchema_(false); maybePostVacuum_(); return publicRanking_(p.callback, p.cmdr);
  }
  var token = PropertiesService.getScriptProperties().getProperty('FLEET_TOKEN');
  if (!e || !e.parameter || e.parameter.token !== token) return json_({ ok: false, error: 'token' });
  var name = e.parameter.sheet || 'Sitios';
  if (['Sitios', 'Visitas', 'Sesiones', 'Taladros', 'Tramos', 'Precios', 'Zonas', 'Estados'].indexOf(name) < 0) return json_({ ok: false, error: 'sheet' });
  var values = sheet_(name).getDataRange().getValues();
  var head = values.shift();
  var rows = values.map(function (r) { var o = {}; head.forEach(function (h, i) { o[h] = r[i]; }); return o; });
  return json_({ ok: true, rows: rows });
}

// ---------------------------------------------------------------- acceso a la web
// Lista de miembros: hoja de la flota, pestaña "Lista de miembros", columna "NOMBRE COMANDANTE".
// Se puede cambiar con las propiedades del script MIEMBROS_HOJA_ID y MIEMBROS_PESTANA.
var MEMBERS_SHEET_ID = '17Tm3ESKz-rh1XoR3pxdtooN0TlD-3HzvHJW6YJ_TLqY';
var MEMBERS_TAB = 'Lista de miembros';

function normCmdr_(s) {
  s = String(s || '').replace(/^\s*cmdr\s+/i, '');
  if (s.normalize) s = s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  return s.replace(/\s+/g, ' ').trim().toUpperCase();
}

var MEMBERS_COPY_TAB = 'Miembros (copia)';

function members_(fresh) {
  var cache = CacheService.getScriptCache();
  var hit = !fresh && cache.get('members_v1');
  if (hit) return hit.split('\n');
  var names;
  try {
    names = readMembersOriginal_();
    try { saveMembersCopy_(names); } catch (e) { console.warn('No se pudo guardar la copia de miembros: ' + e); }
  } catch (err) {
    // La lista de la flota no se puede leer (borrada, sin permiso...): usamos la copia de nuestra hoja
    names = readMembersCopy_();
    if (!names.length) throw err;
    console.warn('Lista de miembros original no disponible (' + err + '); uso la copia (' + names.length + ')');
  }
  cache.put('members_v1', names.join('\n'), 600);   // 10 min: los cambios en la lista tardan eso en notarse
  return names;
}

// Copia de respaldo en la pestaña "Miembros (copia)": se actualiza sola cuando cambia la lista original.
// Si la original desaparece, la web sigue funcionando con esta copia (y se puede editar a mano).
function saveMembersCopy_(names) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(MEMBERS_COPY_TAB);
  if (sh && readMembersCopy_().join('\n') === names.join('\n')) return false;
  if (!sh) sh = ss.insertSheet(MEMBERS_COPY_TAB);
  sh.clearContents();
  sh.getRange(1, 1, 1, 2).setValues([['NOMBRE COMANDANTE', 'Copia automática de la lista de la flota · ' +
    Utilities.formatDate(new Date(), 'Europe/Madrid', 'dd/MM/yyyy HH:mm')]]);
  sh.getRange(2, 1, names.length, 1).setValues(names.map(function (n) { return [n]; }));
  return true;
}

function readMembersCopy_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(MEMBERS_COPY_TAB);
  if (!sh || sh.getLastRow() < 2) return [];
  var out = [];
  sh.getRange(2, 1, sh.getLastRow() - 1, 1).getDisplayValues().forEach(function (r) {
    var n = normCmdr_(r[0]);
    if (n && out.indexOf(n) < 0) out.push(n);
  });
  return out;
}

function readMembersOriginal_() {
  var props = PropertiesService.getScriptProperties();
  var ss = SpreadsheetApp.openById(props.getProperty('MIEMBROS_HOJA_ID') || MEMBERS_SHEET_ID);
  var sh = ss.getSheetByName(props.getProperty('MIEMBROS_PESTANA') || MEMBERS_TAB);
  if (!sh) throw new Error('No encuentro la pestaña de miembros');
  var v = sh.getDataRange().getDisplayValues(), col = -1, row = -1;
  for (var r = 0; r < Math.min(v.length, 15) && col < 0; r++) {
    for (var c = 0; c < v[r].length; c++) {
      if (normCmdr_(v[r][c]) === 'NOMBRE COMANDANTE') { col = c; row = r; break; }
    }
  }
  if (col < 0) throw new Error('No encuentro la columna NOMBRE COMANDANTE');
  var names = [];
  for (var i = row + 1; i < v.length; i++) {
    var n = normCmdr_(v[i][col]);
    if (n && names.indexOf(n) < 0) names.push(n);
  }
  if (!names.length) throw new Error('La lista de miembros está vacía');
  return names;
}

function checkAccess_(cmdr, key) {
  var token = PropertiesService.getScriptProperties().getProperty('FLEET_TOKEN');
  if (!token || String(key || '') !== token) return { ok: false, error: 'auth' };
  var name = normCmdr_(cmdr);
  if (!name) return { ok: false, error: 'auth' };
  var list;
  try { list = members_(); } catch (err) { return { ok: false, error: 'members', detail: String(err.message || err) }; }
  if (list.indexOf(name) < 0) return { ok: false, error: 'member' };
  return { ok: true };
}

// Ejecútala a mano desde el editor para comprobar que el script puede leer la lista (y dar permiso la primera vez)
function probarListaMiembros() {
  var names = readMembersOriginal_();
  Logger.log('Miembros leídos: ' + names.length + ' (primeros: ' + names.slice(0, 5).join(', ') + ')');
  Logger.log(saveMembersCopy_(names) ? 'Copia guardada en la pestaña "' + MEMBERS_COPY_TAB + '"' : 'La copia ya estaba al día');
  CacheService.getScriptCache().remove('members_v1');
}

var PUBLIC_SITE_FIELDS = {
  'SiteID': 'id', 'Sistema': 'system', 'Cuerpo': 'body', 'Mineral': 'mineral', 'Nombre interno': 'type',
  'Precio (Cr)': 'price', 'Lat': 'lat', 'Lon': 'lon', 'Máx taladros': 'rigs',
  'Dist. mín entre taladros (m)': 'rigSpacing', 'Extensión (m)': 'extent', 'T/recogida': 'tpc',
  'Valor por vuelta (Cr)': 'value', 'Visitas': 'visits', 'Recogidas': 'collections',
  'Toneladas totales': 'tonnes', 'Sitio más cercano (m)': 'nearest', 'Mismo mineral más cercano (m)': 'nearestSame',
  'Terreno zona': 'terrain', 'Vel. efectiva zona (m/s)': 'speed', 'Señal zona': 'signal',
  'Sitios minería en cuerpo': 'bodySites', 'Tipo planeta': 'planetClass', 'Gravedad (g)': 'gravity',
  'Temp (K)': 'temp', 'Última visita': 'lastVisit', 'Zona': 'zone', 'Densidad': 'density',
  'Densidad fecha': 'densityTime', 'Agotado': 'depleted', 'Cantidad': 'amount', 'Cantidad fecha': 'amountTime',
  'Cantidad t flota': 'amountTonnes', 'Agotado desde': 'depletedSince', 'Regenerado': 'regenerated',
  'Creado': 'created', 'Cr/h': 'crh'
};

function publicRanking_(callback, cmdr) {
  var values = sheet_('Sitios').getDataRange().getValues();
  var head = values.shift();
  var sites = values.filter(function (r) { return r[0]; }).map(function (r) {
    var o = {};
    head.forEach(function (h, i) {
      var k = PUBLIC_SITE_FIELDS[h];
      if (!k) return;
      var v = r[i];
      if (v instanceof Date) v = v.toISOString();
      o[k] = v === '' ? null : v;
    });
    return o;
  });
  // Vulcanismo de cada cuerpo (pestaña Cuerpos), para el tipo de suelo en la web
  var volc = {};
  var cv = sheet_('Cuerpos').getDataRange().getValues();
  var cvi = cv[0].indexOf('Vulcanismo'), cpi = cv[0].indexOf('Tipo planeta');
  cv.slice(1).forEach(function (r) {
    volc[r[0] + '|' + r[1]] = { v: cvi >= 0 ? String(r[cvi] || '') : '', pc: cpi >= 0 ? String(r[cpi] || '') : '' };
  });
  sites.forEach(function (o) {
    var b = volc[o.system + '|' + o.body];
    if (!b) return;
    o.volcanism = b.v || null;
    if (!o.planetClass && b.pc) o.planetClass = b.pc;
  });
  var ses = sheet_('Sesiones').getDataRange().getValues().slice(1);
  var cmdrs = {};
  var tonnes = 0;
  ses.forEach(function (r) { if (r[3]) cmdrs[r[3]] = 1; tonnes += Number(r[17]) || 0; });
  var zv = sheet_('Zonas').getDataRange().getValues();
  var ZH = zv.shift();
  var zc = function (n) { return ZH.indexOf(n); };
  var zones = zv.filter(function (r) { return r[0]; }).map(function (r) {
    var best = r[zc('Mejor valor por vuelta (Cr)')];
    return { system: r[zc('Sistema')], body: r[zc('Cuerpo')], zone: r[zc('Zona')],
             minerals: String(r[zc('Minerales (anotar a mano)')] || ''), confirmed: String(r[zc('Minerales confirmados')] || ''),
             sites: Number(r[zc('Sitios')]) || 0, best: best === '' ? null : best };
  });
  // Nombre en inglés de cada mineral (para buscar mercados) y mejores ventas reales de la flota
  var names = {};
  sheet_('Precios').getDataRange().getValues().slice(1).forEach(function (r) { if (r[0] && r[2]) names[String(r[0]).toLowerCase()] = r[2]; });
  var sales = {};
  sheet_('Ventas').getDataRange().getValues().slice(1).forEach(function (r) {
    var t = String(r[2] || '').toLowerCase(), price = Number(r[5]) || 0;
    if (!t || !price) return;
    var when = r[0] instanceof Date ? r[0].toISOString() : String(r[0]);
    var o = sales[t] || (sales[t] = { best: 0, bestSystem: '', last: 0, lastSystem: '', lastTime: '', tonnes: 0 });
    o.tonnes += Number(r[4]) || 0;
    if (price > o.best) { o.best = price; o.bestSystem = r[7] || ''; }
    if (!o.lastTime || timeOf_(when) >= timeOf_(o.lastTime)) { o.last = price; o.lastSystem = r[7] || ''; o.lastTime = when; }
  });
  // Regeneraciones vistas por la flota: tiempo (en días) entre agotarse y verse regenerado
  var rg = sheet_('Regeneraciones').getDataRange().getValues();
  var RH = rg.shift();
  var mins = [], maxs = [];
  rg.forEach(function (r) {
    if (!r[0]) return;
    var a = Number(r[RH.indexOf('Días mín')]), b = Number(r[RH.indexOf('Días máx')]);
    if (!isNaN(b) && r[RH.indexOf('Días máx')] !== '') { maxs.push(b); mins.push(isNaN(a) ? 0 : a); }
  });
  var med = function (v) {
    if (!v.length) return null;
    v = v.slice().sort(function (x, y) { return x - y; });
    var m = Math.floor(v.length / 2);
    return v.length % 2 ? v[m] : round_((v[m - 1] + v[m]) / 2, 1);
  };
  // Comandantes que más sitios han descubierto (nombre sin "CMDR " delante; cada sitio cuenta una vez)
  var di = head.indexOf('Descubierto por'), by = {};
  values.forEach(function (r) {
    if (!r[0] || di < 0) return;
    var raw = String(r[di] || '').replace(/^\s*cmdr\s+/i, '').trim();
    if (!raw) return;
    var k = raw.toLowerCase();
    (by[k] = by[k] || { name: raw, sites: 0 }).sites++;
  });
  var cmdrList = Object.keys(by).map(function (k) { return by[k]; })
    .sort(function (a, b) { return b.sites - a.sites || a.name.localeCompare(b.name); }).slice(0, 20);
  var out = { ok: true, updated: new Date().toISOString(), sites: sites, zones: zones, names: names, sales: sales, cmdrs: cmdrList,
              mine: myContributions_(cmdr, values, head), vacuum: vacuum_(ses),
              regen: { n: maxs.length, minDays: med(mins), maxDays: med(maxs) },
              stats: { sites: sites.length, sessions: ses.length, commanders: Object.keys(cmdrs).length, tonnes: tonnes } };
  var txt = JSON.stringify(out);
  if (callback && /^[A-Za-z_$][\w$.]{0,60}$/.test(callback)) {
    return ContentService.createTextOutput(callback + '(' + txt + ');').setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService.createTextOutput(txt).setMimeType(ContentService.MimeType.JSON);
}

// ------------------------------------------------------- Aspirador de la Semana
// Semana de Frontier: del jueves a las 07:00 UTC (reinicio semanal de los servidores) al jueves siguiente.
var WEEK_RESET_DAY = 4;          // 0 = domingo … 4 = jueves
var WEEK_RESET_HOUR_UTC = 7;
var VACUUM_GRACE_H = 3;          // espera tras el reinicio antes de dar el premio (envíos que llegan tarde)

function weekStart_(t) {
  var d = new Date(t);
  var s = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), WEEK_RESET_HOUR_UTC);
  s -= ((d.getUTCDay() - WEEK_RESET_DAY + 7) % 7) * 864e5;
  if (s > t) s -= 7 * 864e5;
  return s;
}

// Toneladas minadas por cada CMDR entre from y to (por la hora de fin de cada sesión)
function vacuumTop_(ses, from, to) {
  var by = {};
  ses.forEach(function (r) {
    var t = timeOf_(r[7]) || timeOf_(r[6]) || timeOf_(r[2]);
    var tn = Number(r[17]) || 0;
    if (!t || t < from || t >= to || tn <= 0) return;
    var name = String(r[3] || '').replace(/^\s*cmdr\s+/i, '').trim();
    if (!name) return;
    var k = name.toLowerCase();
    var o = by[k] || (by[k] = { name: name, tonnes: 0, sessions: 0 });
    o.tonnes += tn; o.sessions++;
  });
  return Object.keys(by).map(function (k) { by[k].tonnes = round_(by[k].tonnes, 1); return by[k]; })
    .sort(function (a, b) { return b.tonnes - a.tonnes || a.name.localeCompare(b.name); }).slice(0, 3);
}

function vacuum_(ses) {
  var now = Date.now(), cur = weekStart_(now), prev = cur - 7 * 864e5;
  return { last: { start: new Date(prev).toISOString(), end: new Date(cur).toISOString(), top: vacuumTop_(ses, prev, cur) },
           current: { start: new Date(cur).toISOString(), top: vacuumTop_(ses, cur, now + 1) } };
}

// Publica en Discord, una sola vez por semana, el Aspirador de la semana que acaba de terminar.
// Se comprueba al recibir datos del plugin o al abrir la web (no hace falta ningún activador).
function maybePostVacuum_() {
  try {
    var now = Date.now(), cur = weekStart_(now);
    if (now < cur + VACUUM_GRACE_H * 3600e3) return;
    var key = new Date(cur - 7 * 864e5).toISOString().slice(0, 10);
    var props = PropertiesService.getScriptProperties();
    if (props.getProperty('ASPIRADOR_PUBLICADO') === key) return;
    var lock = LockService.getScriptLock();
    if (!lock.tryLock(5000)) return;
    try {
      if (props.getProperty('ASPIRADOR_PUBLICADO') === key) return;
      props.setProperty('ASPIRADOR_PUBLICADO', key);
      var cfg = discordConfig_();
      if (!cfg.url || cfg.mode === 'no') return;
      var last = vacuum_(tabValues_('Sesiones').slice(1)).last;
      if (last.top.length) sendDiscord_(vacuumMessage_(last));
    } finally { lock.releaseLock(); }
  } catch (err) { console.warn('Aspirador de la Semana: ' + err); }
}

function vacuumMessage_(w) {
  var f = function (iso) { return Utilities.formatDate(new Date(iso), 'Europe/Madrid', 'dd/MM'); };
  var t = function (x) { return Utilities.formatString('%s t', String(x).replace('.', ',')); };
  var win = w.top[0];
  var desc = '**CMDR ' + win.name + '** ha aspirado **' + t(win.tonnes) + '** de mineral en ' + win.sessions +
    (win.sessions === 1 ? ' sesión' : ' sesiones') + ' del jueves ' + f(w.start) + ' al jueves ' + f(w.end) + ' (de reinicio a reinicio de los servidores).\n' +
    'No queda ni una piedra en los planetas por donde ha pasado. 🌀';
  var medals = ['🥈', '🥉'];
  w.top.slice(1).forEach(function (o, i) { desc += '\n' + medals[i] + ' ' + o.name + ': ' + t(o.tonnes); });
  desc += '\n\nNuevo concurso desde el reinicio del jueves. [Ver la web](' + WEB_URL + ')';
  return { embeds: [{ title: '🏆 Aspirador de la Semana', description: desc, color: 0xff8a1f }] };
}

// Ejecútala a mano para (re)publicar en Discord el Aspirador de la semana pasada
function publicarAspirador() {
  var last = vacuum_(tabValues_('Sesiones').slice(1)).last;
  if (!last.top.length) { Logger.log('Nadie minó la semana pasada (' + last.start + ' → ' + last.end + ')'); return; }
  var ok = sendDiscord_(vacuumMessage_(last));
  PropertiesService.getScriptProperties().setProperty('ASPIRADOR_PUBLICADO', last.start.slice(0, 10));
  Logger.log((ok ? 'Publicado: ' : 'No se pudo enviar a Discord: ') + last.top[0].name + ' ' + last.top[0].tonnes + ' t');
}

// "Mis aportaciones": SiteID de los sitios que este CMDR descubrió, minó o marcó (solo se le devuelven a él)
function myContributions_(cmdr, siteRows, siteHead) {
  var me = normCmdr_(cmdr);
  if (!me) return null;
  var disc = {}, mined = {}, marked = {};
  var di = siteHead.indexOf('Descubierto por');
  siteRows.forEach(function (r) { if (r[0] && di >= 0 && normCmdr_(r[di]) === me) disc[String(r[0])] = 1; });
  var vis = tabValues_('Visitas'), vh = vis[0] || [];
  var vs = vh.indexOf('SiteID'), vc = vh.indexOf('CMDR');
  vis.slice(1).forEach(function (r) { if (vs >= 0 && r[vs] && normCmdr_(r[vc]) === me) mined[String(r[vs])] = 1; });
  var est = tabValues_('Estados'), eh = est[0] || [];
  var es = eh.indexOf('SiteID'), ec = eh.indexOf('CMDR');
  est.slice(1).forEach(function (r) { if (es >= 0 && r[es] && normCmdr_(r[ec]) === me) marked[String(r[es])] = 1; });
  return { discovered: Object.keys(disc), mined: Object.keys(mined), marked: Object.keys(marked) };
}

// ---------------------------------------------------------------------- sesiones
function handleSession_(d) {
  if (findRow_('Sesiones', 1, d.session_id) > 0) return; // duplicado (reintento)
  var s = d.summary || {};
  var prices = priceMap_();
  ensurePrices_(s.tonnes_by_type || {}, s.type_names || {}, prices);
  var esName = esNames_();

  var value = 0, minerals = [];
  Object.keys(s.tonnes_by_type || {}).forEach(function (t) {
    var n = s.tonnes_by_type[t];
    value += n * (prices[t] || 0);
    minerals.push((esName[t] || t) + ' ' + n + 't');
  });
  var hours = (s.duration_s || 0) / 3600;
  var crh = hours > 0.02 ? Math.round(value / hours) : '';
  var mats = Object.keys(d.materials || {}).map(function (k) { return k + ' ' + d.materials[k]; }).join(', ');

  // Zonas: puntos de bajada que ha registrado el plugin
  (d.zones || []).forEach(function (z) { upsertZone_(d.system, d.body, z.index, z.lat, z.lon); });

  // Sitios: uno por grupo de taladros del mismo mineral
  var siteIds = {};
  var news = [];
  (s.sites || []).forEach(function (st) {
    if (st.zone === null || st.zone === undefined) st.zone = nearestZone_(d.system, d.body, st.lat, st.lon, d.planet_radius_m);
    var before = siteSnapshot_(d, st);
    var id = assignSite_(d, st, esName, prices);
    siteIds[st.idx] = id;
    sheet_('Visitas').appendRow([d.session_id, id, d.end, d.cmdr, esName[st.main_type] || st.main_type, st.rigs,
      nz_(st.rig_spacing_min_m), nz_(st.extent_m), st.collections, st.tonnes, nz_(st.tonnes_per_collection),
      s.terrain, nz_(s.eff_speed_median_ms), nz_(st.zone)]);
    news.push({ id: id, st: st, isNew: !before, prevRigs: before ? before.rigs : 0 });
  });
  var ids = Object.keys(siteIds).map(function (k) { return siteIds[k]; });

  sheet_('Sesiones').appendRow([
    d.session_id, ids.join(', '), new Date(), d.cmdr, d.system, d.body, d.start, d.end,
    round_((s.duration_s || 0) / 60, 1), s.rigs, s.collections, nz_(s.tonnes_per_collection),
    s.cycle_s_median ? round_(s.cycle_s_median / 60, 1) : '', nz_(d.site_signal), nz_(d.mining_locations_on_body),
    mats, (d.loads_to_ship || []).join(' + '), s.tonnes, Math.round(value), crh, nz_((s.route || {}).loop_m),
    nz_(s.eff_speed_median_ms), nz_(s.moving_speed_ms), nz_(s.sinuosity_median), s.terrain, s.track_len_m,
    minerals.join(', '), d.planet_class, d.gravity_g, d.temp_k, d.planet_radius_m, d.srv_type, d.close_reason,
    (d.unknown_events || []).join(', '), d.plugin_version,
    (d.zones || []).map(function (z) { return z.index; }).join(', ')
  ]);

  var pl = sheet_('Taladros');
  (s.rig_list || []).forEach(function (r) {
    pl.appendRow([d.session_id, siteIds[r.site] || '', r.idx, r.lat, r.lon, esName[r.main_type] || r.main_type,
                  r.tonnes, r.collections, nz_(r.tonnes_per_collection),
                  new Date(r.first_t * 1000), new Date(r.last_t * 1000)]);
  });
  var tr = sheet_('Tramos');
  (s.segments || []).forEach(function (g) {
    tr.appendRow([d.session_id, g.from, g.to, g.straight_m, g.path_m, g.time_s, nz_(g.eff_speed_ms), nz_(g.sinuosity)]);
  });
  var track = d.track || '';
  var rc = sheet_('Recorridos');
  for (var i = 0, part = 1; i < track.length; i += TRACK_CHUNK, part++) {
    rc.appendRow([d.session_id, part, track.slice(i, i + TRACK_CHUNK)]);
  }
  var raw = d.refined_raw || '';
  if (raw) {
    var rg = sheet_('Recogidas');
    for (var k = 0, pr = 1; k < raw.length; k += TRACK_CHUNK, pr++) {
      rg.appendRow([d.session_id, d.session_start_t || '', pr, raw.slice(k, k + TRACK_CHUNK)]);
    }
  }
  if (d.body) handleBody_({ system: d.system, body: d.body, planet_class: d.planet_class, gravity_g: d.gravity_g,
                            temp_k: d.temp_k, radius_m: d.planet_radius_m, atmosphere: d.atmosphere,
                            mining_locations: d.mining_locations_on_body, cmdr: d.cmdr, volcanism: d.volcanism });
  if (d.body) { try { fillBodyFromSpansh_(d.system, d.body, false); } catch (err) { Logger.log('Spansh cuerpo: ' + err); } }
  ids.forEach(function (id) { recomputeSite_(id, prices); });
  recomputeNearest_(d.system, d.body, d.planet_radius_m);
  recomputeZones_(d.system, d.body);
  try { notifySession_(d, news, esName, prices); } catch (err) { Logger.log('Discord: ' + err); logDiscord_('ERROR', d.system + ' · ' + d.body, String(err)); }
}

// Estado del sitio antes de procesar la sesión (para saber si es nuevo o un récord)
function siteSnapshot_(d, st) {
  var values = sheet_('Sitios').getDataRange().getValues();
  var H = values[0];
  var R = d.planet_radius_m || 0;
  for (var i = 1; i < values.length; i++) {
    var row = values[i];
    if (row[1] !== d.system || row[2] !== d.body || row[4] !== st.main_type || !R) continue;
    if (haversine_(st.lat, st.lon, row[6], row[7], R) <= SITE_MATCH_M) {
      return { rigs: Number(row[H.indexOf('Máx taladros')]) || 0 };
    }
  }
  return null;
}

function assignSite_(d, st, esName, prices) {
  var sh = sheet_('Sitios');
  var H = HEADERS['Sitios'];
  var values = sh.getDataRange().getValues();
  var R = d.planet_radius_m || 0;
  var best = null, bestD = null;
  for (var i = 1; i < values.length; i++) {
    var row = values[i];
    if (row[1] !== d.system || row[2] !== d.body || row[4] !== st.main_type || !R) continue;
    var dist = haversine_(st.lat, st.lon, row[6], row[7], R);
    if (dist <= SITE_MATCH_M && (bestD === null || dist < bestD)) { best = row[0]; bestD = dist; }
  }
  if (best) return best;
  var id = 'S' + Utilities.formatString('%05d', values.length);
  var row = new Array(H.length).fill('');
  var set = function (n, v) { row[H.indexOf(n)] = (v === null || v === undefined) ? '' : v; };
  set('SiteID', id); set('Sistema', d.system); set('Cuerpo', d.body);
  set('Mineral', esName[st.main_type] || st.main_type); set('Nombre interno', st.main_type);
  set('Lat', st.lat); set('Lon', st.lon); set('Señal zona', d.site_signal);
  set('Sitios minería en cuerpo', d.mining_locations_on_body); set('Tipo planeta', d.planet_class);
  set('Gravedad (g)', d.gravity_g); set('Temp (K)', d.temp_k); set('Zona', st.zone); set('Creado', new Date()); set('Descubierto por', d.cmdr);
  sh.appendRow(row);
  applyPendingStates_(id, d.system, d.body, st.main_type, st.lat, st.lon, d.planet_radius_m);
  return id;
}

function recomputeSite_(siteId, prices) {
  var vis = tabValues_('Visitas');
  var VH = vis[0];
  var vc = function (n) { return VH.indexOf(n); };
  var rows = vis.slice(1).filter(function (r) { return r[1] === siteId; });
  var vals = function (n) { return rows.map(function (r) { return r[vc(n)]; }).filter(function (x) { return x !== '' && x !== null; }); };
  var median = function (v) {
    if (!v.length) return '';
    v = v.slice().sort(function (a, b) { return a - b; });
    var m = Math.floor(v.length / 2);
    return v.length % 2 ? v[m] : round_((v[m - 1] + v[m]) / 2, 2);
  };
  var sum = function (v) { return v.reduce(function (a, b) { return a + Number(b); }, 0); };

  var sh = sheet_('Sitios');
  var H = HEADERS['Sitios'];
  var r = findRow_('Sitios', 1, siteId);
  var cur = sh.getRange(r, 1, 1, H.length).getValues()[0];
  var set = function (n, v) { cur[H.indexOf(n)] = v; };
  var price = prices[String(cur[H.indexOf('Nombre interno')]).toLowerCase()] || 0;
  var declared = Number(cur[H.indexOf('Taladros marcados')]) || 0;
  var maxRigs = Math.max.apply(null, vals('Taladros').concat([declared]));
  var spacing = vals('Dist. mín entre taladros (m)');
  var tpc = median(vals('T/recogida'));
  var votes = {};
  vals('Terreno zona').forEach(function (t) { if (t !== 'sin datos') votes[t] = (votes[t] || 0) + 1; });

  set('Precio (Cr)', price);
  set('Máx taladros', maxRigs);
  set('Dist. mín entre taladros (m)', spacing.length ? Math.min.apply(null, spacing) : '');
  set('Extensión (m)', Math.max.apply(null, vals('Extensión (m)').concat([0])));
  set('T/recogida', tpc);
  // Valor de recoger todos los taladros una vez: la cifra para comparar sitios
  // Sin recogidas (sitio solo marcado con el formulario): se supone un taladro lleno, ~11,5 t
  set('Valor por vuelta (Cr)', maxRigs ? Math.round(maxRigs * (tpc !== '' ? tpc : MARK_TPC) * price) : '');
  set('Visitas', rows.length);
  // Cr/h del sitio: mediana del Cr/h de las sesiones que lo visitaron (mejor las que solo minaron ese sitio)
  var ses = tabValues_('Sesiones').slice();
  var SH = ses.shift();
  var ciS = SH.indexOf('Sitios'), ciC = SH.indexOf('Cr/h');
  var mine = ses.filter(function (x) {
    return String(x[ciS]).split(',').map(function (z) { return z.trim(); }).indexOf(siteId) >= 0 && Number(x[ciC]) > 0;
  });
  var solo = mine.filter(function (x) { return String(x[ciS]).indexOf(',') < 0; });
  var crhList = (solo.length ? solo : mine).map(function (x) { return Number(x[ciC]); });
  set('Cr/h', crhList.length ? Math.round(median(crhList)) : '');
  // Fecha de creación: la primera visita; si no hay, la última visita o la fecha de hoy
  if (cur[H.indexOf('Creado')] === '' || cur[H.indexOf('Creado')] === null) {
    var firstV = rows.length ? rows.map(function (x) { return timeOf_(x[vc('Fecha')]); }).filter(Boolean).sort()[0] : 0;
    var lastV = timeOf_(cur[H.indexOf('Última visita')]);
    set('Creado', new Date(firstV || lastV || Date.now()));
  }
  // Descubierto por: quien lo minó primero; si solo está marcado, quien lo marcó
  if (!cur[H.indexOf('Descubierto por')]) {
    var firstRow = rows.slice().sort(function (a, b) { return timeOf_(a[vc('Fecha')]) - timeOf_(b[vc('Fecha')]); })[0];
    set('Descubierto por', firstRow ? firstRow[vc('CMDR')] : cur[H.indexOf('Último CMDR')]);
  }
  if (!rows.length) { sh.getRange(r, 1, 1, H.length).setValues([cur]); return; }
  set('Recogidas', sum(vals('Recogidas')));
  set('Toneladas totales', sum(vals('Toneladas')));
  set('Terreno zona', Object.keys(votes).sort(function (a, b) { return votes[b] - votes[a]; })[0] || 'sin datos');
  set('Vel. efectiva zona (m/s)', median(vals('Vel. efectiva zona (m/s)')));
  set('Última visita', rows[rows.length - 1][vc('Fecha')]);
  set('Último CMDR', rows[rows.length - 1][vc('CMDR')]);
  var zones = vals('Zona');
  if (zones.length) set('Zona', zones[zones.length - 1]);
  sh.getRange(r, 1, 1, H.length).setValues([cur]);
}

// ------------------------------------------------------------------------- zonas
function upsertZone_(system, body, index, lat, lon) {
  if (index === null || index === undefined || !system || !body) return;
  var sh = sheet_('Zonas');
  var v = sh.getDataRange().getValues();
  for (var i = 1; i < v.length; i++) {
    if (v[i][0] === system && v[i][1] === body && Number(v[i][2]) === Number(index)) {
      if (v[i][3] === '' && lat !== undefined) sh.getRange(i + 1, 4, 1, 2).setValues([[lat, lon]]);
      return;
    }
  }
  var row = new Array(HEADERS['Zonas'].length).fill('');
  row[0] = system; row[1] = body; row[2] = Number(index); row[3] = nz_(lat); row[4] = nz_(lon); row[9] = new Date();
  sh.appendRow(row);
}

function nearestZone_(system, body, lat, lon, R) {
  if (!R || lat === null || lat === undefined) return '';
  var v = sheet_('Zonas').getDataRange().getValues();
  var best = '', bestD = null;
  for (var i = 1; i < v.length; i++) {
    if (v[i][0] !== system || v[i][1] !== body || v[i][3] === '') continue;
    var dd = haversine_(lat, lon, v[i][3], v[i][4], R);
    if (dd <= ZONE_RADIUS_M && (bestD === null || dd < bestD)) { best = v[i][2]; bestD = dd; }
  }
  return best;
}

// Minerales confirmados, nº de sitios y mejor valor de cada zona del cuerpo
function recomputeZones_(system, body) {
  var sites = sheet_('Sitios').getDataRange().getValues();
  var H = sites.shift();
  var c = function (n) { return H.indexOf(n); };
  var sh = sheet_('Zonas');
  var z = sh.getDataRange().getValues();
  // zonas que aparecen en sitios pero aún no están en la pestaña Zonas
  var known = {};
  for (var i = 1; i < z.length; i++) if (z[i][0] === system && z[i][1] === body) known[String(z[i][2])] = 1;
  sites.forEach(function (r) {
    var zn = r[c('Zona')];
    if (r[1] === system && r[2] === body && zn !== '' && !known[String(zn)]) { upsertZone_(system, body, zn); known[String(zn)] = 1; }
  });
  z = sh.getDataRange().getValues();
  for (var j = 1; j < z.length; j++) {
    if (z[j][0] !== system || z[j][1] !== body) continue;
    var mine = sites.filter(function (r) { return r[1] === system && r[2] === body && String(r[c('Zona')]) === String(z[j][2]); });
    var minerals = {};
    var best = '';
    mine.forEach(function (r) {
      minerals[r[c('Mineral')]] = 1;
      var v = r[c('Valor por vuelta (Cr)')];
      if (v !== '' && (best === '' || v > best)) best = v;
    });
    sh.getRange(j + 1, 7, 1, 4).setValues([[Object.keys(minerals).join(', '), mine.length, best, new Date()]]);
  }
}

// --------------------------------------------------------- formulario de sitio
// El plugin (v0.6.0+) envía "mark": sitio, mineral, taladros, cantidad y densidad leídos en el escáner,
// aunque no se haya minado. Si el sitio no existe, se crea; los estados van por handleState_.
var MARK_TPC = 11.5;
var MARK_DENSITY = { Alta: 'alto', Media: 'medio', Baja: 'bajo' };
var MARK_AMOUNT = { Alta: 'cant_alta', Media: 'cant_media', Baja: 'cant_baja', Agotado: 'agotado' };

function handleMark_(d) {
  if (!d.type || !d.planet_radius_m || d.lat == null) return;
  var esName = esNames_(), prices = priceMap_();
  var created = false;
  var siteId = findSiteNear_(d.system, d.body, d.type, d.lat, d.lon, d.planet_radius_m);
  if (!siteId) {
    var sh = sheet_('Sitios'), H = HEADERS['Sitios'];
    siteId = 'S' + Utilities.formatString('%05d', sh.getLastRow());
    var row = new Array(H.length).fill('');
    var set = function (n, v) { row[H.indexOf(n)] = (v === null || v === undefined) ? '' : v; };
    set('SiteID', siteId); set('Sistema', d.system); set('Cuerpo', d.body);
    set('Mineral', esName[d.type] || d.type); set('Nombre interno', d.type);
    set('Lat', d.lat); set('Lon', d.lon); set('Señal zona', d.site_signal);
    set('Sitios minería en cuerpo', d.mining_locations_on_body); set('Tipo planeta', d.planet_class);
    set('Gravedad (g)', d.gravity_g); set('Temp (K)', d.temp_k); set('Zona', d.zone);
    set('Visitas', 0); set('Recogidas', 0); set('Toneladas totales', 0); set('Terreno zona', 'sin datos');
    set('Última visita', d.time); set('Último CMDR', d.cmdr); set('Creado', new Date()); set('Descubierto por', d.cmdr);
    sh.appendRow(row);
    created = true;
    if (d.body) handleBody_({ system: d.system, body: d.body, planet_class: d.planet_class, gravity_g: d.gravity_g,
                              temp_k: d.temp_k, radius_m: d.planet_radius_m, mining_locations: d.mining_locations_on_body,
                              cmdr: d.cmdr, volcanism: d.volcanism });
  }
  var sh2 = sheet_('Sitios'), H2 = HEADERS['Sitios'], r = findRow_('Sitios', 1, siteId);
  if (d.rigs) {
    var c = H2.indexOf('Taladros marcados') + 1, old = Number(sh2.getRange(r, c).getValue()) || 0;
    if (d.rigs > old) sh2.getRange(r, c).setValue(d.rigs);
  }
  if (d.zone !== null && d.zone !== undefined && d.zone !== '') {
    var cz = H2.indexOf('Zona') + 1;
    if (sh2.getRange(r, cz).getValue() === '') sh2.getRange(r, cz).setValue(d.zone);
  }
  recomputeSite_(siteId, prices);
  // Densidad y cantidad, como si se hubieran pulsado los botones (historial en Estados)
  var base = { time: d.time, cmdr: d.cmdr, system: d.system, body: d.body, zone: d.zone, lat: d.lat, lon: d.lon,
               type: d.type, planet_radius_m: d.planet_radius_m, session_tonnes: d.session_tonnes };
  if (MARK_DENSITY[d.density]) handleState_(Object.assign({}, base, { state: MARK_DENSITY[d.density] }));
  if (MARK_AMOUNT[d.amount]) handleState_(Object.assign({}, base, { state: MARK_AMOUNT[d.amount] }));
  if (d.zone !== null && d.zone !== undefined && d.zone !== '') upsertZone_(d.system, d.body, d.zone);
  recomputeNearest_(d.system, d.body, d.planet_radius_m);
  if (created) {
    try {
      var cfg = discordConfig_(), row2 = siteRow_(siteId);
      if (cfg.url && cfg.mode !== 'no' && row2) {
        sendDiscord_({ embeds: [siteEmbed_('📌 Sitio marcado: ' + row2['Mineral'] + ' (' + credits_(row2['Precio (Cr)']) + '/t)',
                                           0xb28dff, row2, d.cmdr)] });
      }
    } catch (err) { Logger.log('Discord: ' + err); logDiscord_('ERROR', d.system + ' · ' + d.body, String(err)); }
  }
}

// ----------------------------------------------------------------------- estados
function handleState_(d) {
  var label = STATE_LABELS[d.state];
  if (!label) return;
  var esName = esNames_();
  var siteId = findSiteNear_(d.system, d.body, d.type, d.lat, d.lon, d.planet_radius_m);
  // Toneladas que la flota llevaba sacadas del sitio al marcar: las ya registradas + las de la sesión en curso
  var sesT = Number(d.session_tonnes) || 0;
  var prev = 0;
  if (siteId) { var row = siteRow_(siteId); prev = row ? Number(row['Toneladas totales']) || 0 : 0; }
  sheet_('Estados').appendRow([d.time, d.cmdr, d.system, d.body, nz_(d.zone), d.lat, d.lon,
                               d.type ? (esName[d.type] || d.type) : '', label, siteId || '', sesT, prev + sesT]);
  var regen = siteId ? setSiteState_(siteId, label, d.time, d.cmdr, prev + sesT) : null;
  if (d.zone !== null && d.zone !== undefined) upsertZone_(d.system, d.body, d.zone);
  try { notifyState_(d, label, siteId, esName); } catch (err) { Logger.log('Discord: ' + err); }
  try { if (regen && regen.isNew) notifyRegen_(regen); } catch (err) { Logger.log('Discord: ' + err); }
}

function findSiteNear_(system, body, type, lat, lon, R) {
  if (!R) return null;
  var v = sheet_('Sitios').getDataRange().getValues();
  var best = null, bestD = null;
  for (var i = 1; i < v.length; i++) {
    if (v[i][1] !== system || v[i][2] !== body) continue;
    if (type && v[i][4] !== type) continue;
    var dd = haversine_(lat, lon, v[i][6], v[i][7], R);
    if (dd <= SITE_MATCH_M && (bestD === null || dd < bestD)) { best = v[i][0]; bestD = dd; }
  }
  return best;
}

// Densidad = la última marcada. Agotado = fecha de la última marca de agotado, salvo que
// después alguien haya marcado una densidad (el sitio seguía activo o fue un error).
// Densidad: fija, la última marcada. Cantidad ("Mineral amount" del escáner): lo que queda, con las
// toneladas que llevaba la flota al marcarla. Agotado: fecha; se quita si luego alguien marca una cantidad.
function setSiteState_(siteId, label, when, cmdr, fleetT) {
  var sh = sheet_('Sitios');
  var H = HEADERS['Sitios'];
  var r = findRow_('Sitios', 1, siteId);
  if (r < 0) return;
  var t = fleetT === '' || fleetT === undefined || fleetT === null ? '' : fleetT;
  var col = function (n) { return H.indexOf(n) + 1; };
  var regen = null;
  if (label === 'Agotado') {
    var oldAg = sh.getRange(r, col('Agotado')).getValue();
    // Primera marca de este agotamiento: guarda desde cuándo y borra la regeneración anterior
    if (oldAg === '' || oldAg === null) {
      sh.getRange(r, col('Agotado desde')).setValue(when);
      sh.getRange(r, col('Regenerado'), 1, 2).setValues([['', '']]);
    }
    sh.getRange(r, col('Agotado'), 1, 2).setValues([[when, cmdr || '']]);
    sh.getRange(r, col('Cantidad'), 1, 4).setValues([['Agotada', when, cmdr || '', t]]);
  } else if (/^Cantidad /.test(label)) {
    var q = label.replace('Cantidad ', '');
    var seen = sh.getRange(r, col('Agotado')).getValue();            // última vez visto agotado
    var since = sh.getRange(r, col('Agotado desde')).getValue() || seen;
    sh.getRange(r, col('Cantidad'), 1, 4).setValues([[q.charAt(0).toUpperCase() + q.slice(1), when, cmdr || '', t]]);
    sh.getRange(r, col('Agotado'), 1, 2).setValues([['', '']]);
    sh.getRange(r, col('Agotado desde')).setValue('');
    // Estaba agotado y ahora tiene cantidad: regenerado (salvo que fuera una corrección enseguida)
    if (seen !== '' && seen !== null && timeOf_(when) - timeOf_(seen) >= REGEN_MIN_H * 3600e3) {
      var key = siteId + '|' + timeOf_(when);
      var rs = sheet_('Regeneraciones'), rv = rs.getDataRange().getValues();
      var dup = false;
      for (var i = 1; i < rv.length; i++) if (rv[i][0] + '|' + timeOf_(rv[i][6]) === key) { dup = true; break; }
      var row = siteRow_(siteId) || {};
      var days = function (a, b) { return round_((timeOf_(b) - timeOf_(a)) / 86400e3, 1); };
      regen = { siteId: siteId, mineral: row['Mineral'], system: row['Sistema'], body: row['Cuerpo'], cmdr: cmdr || '',
                since: since, seen: seen, when: when, minDays: days(since, seen), maxDays: days(since, when), isNew: !dup };
      sh.getRange(r, col('Regenerado'), 1, 2).setValues([[when, cmdr || '']]);
      if (!dup) rs.appendRow([siteId, row['Sistema'], row['Cuerpo'], row['Mineral'], since, seen, when, cmdr || '',
                              regen.minDays, regen.maxDays]);
    }
  } else {
    sh.getRange(r, col('Densidad'), 1, 3).setValues([[OLD_DENSITY[label] || label, when, cmdr || '']]);
  }
  return regen;
}

// Recalcula densidad y agotado de un sitio (o de todos) a partir del historial de la pestaña Estados.
function recomputeSiteStates_(siteId) {
  var v = sheet_('Estados').getDataRange().getValues().slice(1)
    .filter(function (r) { return r[9] && (!siteId || r[9] === siteId); })
    .sort(function (a, b) { return timeOf_(a[0]) - timeOf_(b[0]); });
  var seen = {};
  v.forEach(function (r) { seen[r[9]] = 1; setSiteState_(r[9], r[8], r[0], r[1], r[11]); });
  return seen;
}

// Lectura de una pestaña entera; durante recalcularSitios se lee una sola vez y se reutiliza (Google corta si se lee cientos de veces)
var TAB_CACHE_ = null;
function tabValues_(name) {
  if (TAB_CACHE_ && TAB_CACHE_[name]) return TAB_CACHE_[name];
  return sheet_(name).getDataRange().getValues();
}

// Ejecutar a mano tras actualizar el script: rellena Cr/h y Creado de todos los sitios ya existentes.
// Se puede ejecutar más de una vez sin problema: reintenta cada sitio y avisa de los que no pudo.
function recalcularSitios() {
  ensureSchema_(true);
  var prices = priceMap_();
  var ids = sheet_('Sitios').getDataRange().getValues().slice(1).map(function (r) { return r[0]; }).filter(String);
  TAB_CACHE_ = { Visitas: sheet_('Visitas').getDataRange().getValues(), Sesiones: sheet_('Sesiones').getDataRange().getValues() };
  var ok = 0, failed = [];
  try {
    ids.forEach(function (id) {
      for (var t = 1; t <= 3; t++) {
        try { recomputeSite_(id, prices); ok++; return; }
        catch (err) { if (t === 3) failed.push(id + ' (' + String(err).slice(0, 80) + ')'); else Utilities.sleep(1500 * t); }
      }
    });
  } finally { TAB_CACHE_ = null; }
  Logger.log('Sitios recalculados: ' + ok + ' de ' + ids.length + (failed.length ? '. Fallaron: ' + failed.join('; ') + ' — vuelve a ejecutar la función.' : ''));
}

function recomputeAllStates_() {
  // Primero, pasar los datos de la columna vieja "Estado" a su sitio nuevo.
  var sh = sheet_('Sitios');
  var H = HEADERS['Sitios'];
  var v = sh.getDataRange().getValues();
  var cD = H.indexOf('Densidad');
  for (var i = 1; i < v.length; i++) {
    var d = v[i][cD];
    if (!v[i][0]) continue;
    if (d === 'Agotado') {
      sh.getRange(i + 1, cD + 1, 1, 5).setValues([['', '', '', v[i][cD + 1], v[i][cD + 2]]]);
    } else if (OLD_DENSITY[d]) {
      sh.getRange(i + 1, cD + 1).setValue(OLD_DENSITY[d]);
    }
  }
  // Después, rehacer con el historial completo de la pestaña Estados.
  recomputeSiteStates_(null);
}

// Estados marcados antes de que existiera el sitio (se marcó al escanear, antes de minar)
function applyPendingStates_(siteId, system, body, type, lat, lon, R) {
  if (!R) return;
  var sh = sheet_('Estados');
  var v = sh.getDataRange().getValues();
  var esName = esNames_();
  var found = false;
  for (var i = 1; i < v.length; i++) {
    if (v[i][9] || v[i][2] !== system || v[i][3] !== body) continue;
    if (v[i][7] && v[i][7] !== (esName[type] || type)) continue;
    if (haversine_(lat, lon, v[i][5], v[i][6], R) > SITE_MATCH_M) continue;
    sh.getRange(i + 1, 10).setValue(siteId);
    found = true;
  }
  if (found) recomputeSiteStates_(siteId);
}

// ----------------------------------------------------------------------- discord
// Configuración en Propiedades del script:
//   DISCORD_WEBHOOK = URL del webhook del canal (no la compartas)
//   DISCORD_MODE    = novedades (sitio nuevo o récord de taladros) | sesiones | no
//   DISCORD_ESTADOS = si  → avisar también cuando alguien marca un sitio como Agotado
function discordConfig_() {
  var p = PropertiesService.getScriptProperties();
  return { url: p.getProperty('DISCORD_WEBHOOK') || '', mode: (p.getProperty('DISCORD_MODE') || 'novedades').toLowerCase(),
           states: (p.getProperty('DISCORD_ESTADOS') || 'no').toLowerCase() === 'si' };
}

function sendDiscord_(payload) {
  var cfg = discordConfig_();
  if (!cfg.url) return false;
  payload.username = payload.username || 'Skull Mining';
  var res = UrlFetchApp.fetch(cfg.url, { method: 'post', contentType: 'application/json',
                                         payload: JSON.stringify(payload), muteHttpExceptions: true });
  var code = res.getResponseCode();
  var title = ((payload.embeds || [])[0] || {}).title || payload.content || '';
  logDiscord_(code < 300 ? 'enviado' : 'RECHAZADO ' + code, title, code < 300 ? '' : res.getContentText().slice(0, 400));
  return code < 300;
}

// Registro de avisos a Discord en la pestaña "Registro Discord" (las 200 últimas líneas)
function logDiscord_(result, title, detail) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sh = ss.getSheetByName('Registro Discord');
    if (!sh) { sh = ss.insertSheet('Registro Discord'); sh.appendRow(['Fecha', 'Resultado', 'Aviso', 'Detalle']); sh.setFrozenRows(1); }
    sh.appendRow([new Date(), result, String(title).slice(0, 200), String(detail || '').slice(0, 400)]);
    if (sh.getLastRow() > 220) sh.deleteRows(2, sh.getLastRow() - 201);
  } catch (e) { Logger.log('Registro Discord: ' + e); }
}

// Ejecutar a mano: manda a Discord el aviso del sitio visitado más recientemente (prueba con datos reales)
function probarAvisoSitio() {
  var v = sheet_('Sitios').getDataRange().getValues();
  var H = v[0], c = H.indexOf('Última visita'), best = null;
  for (var i = 1; i < v.length; i++) if (v[i][0] && (!best || timeOf_(v[i][c]) > timeOf_(best[c]))) best = v[i];
  if (!best) { Logger.log('No hay sitios'); return; }
  var row = siteRow_(best[0]);
  var ok = sendDiscord_({ embeds: [siteEmbed_('🧪 Prueba: ' + row['Mineral'] + ' (' + credits_(row['Precio (Cr)']) + '/t)', 0x4fd1ff, row, row['Último CMDR'])] });
  Logger.log((ok ? 'Enviado: ' : 'RECHAZADO: ') + row['Mineral'] + ' en ' + row['Cuerpo'] + ' — mira la pestaña Registro Discord');
}

function credits_(v) {
  v = Number(v) || 0;
  if (v >= 1e6) return (Math.round(v / 1e4) / 100).toString().replace('.', ',') + ' M Cr';
  if (v >= 1e3) return Math.round(v / 1e3) + ' k Cr';
  return v + ' Cr';
}

function siteRow_(siteId) {
  var v = sheet_('Sitios').getDataRange().getValues();
  var H = v[0];
  for (var i = 1; i < v.length; i++) if (v[i][0] === siteId) {
    var o = {};
    H.forEach(function (h, k) { o[h] = v[i][k]; });
    return o;
  }
  return null;
}

function siteEmbed_(title, color, row, cmdr) {
  var zona = row['Zona'] !== '' ? 'Zona ' + row['Zona'] + (row['Sitios minería en cuerpo'] ? ' de ' + row['Sitios minería en cuerpo'] : '') : 'zona sin identificar';
  return {
    title: title, url: WEB_URL, color: color,
    description: '📍 **' + row['Sistema'] + '** · ' + row['Cuerpo'] + ' · ' + zona +
      '\n🧭 ' + Number(row['Lat']).toFixed(4) + ', ' + Number(row['Lon']).toFixed(4),
    fields: [
      { name: 'Taladros', value: String(row['Máx taladros'] || 0), inline: true },
      { name: 'Valor por vuelta', value: credits_(row['Valor por vuelta (Cr)']), inline: true },
      { name: 'Terreno', value: String(row['Terreno zona'] || 'sin datos'), inline: true },
      { name: 'Densidad', value: String(row['Densidad'] || 'sin marcar'), inline: true }
    ],
    footer: { text: (cmdr ? (/^cmdr /i.test(cmdr) ? cmdr : 'CMDR ' + cmdr) + ' · ' : '') + 'Skull Mining' }
  };
}

function notifySession_(d, news, esName, prices) {
  var cfg = discordConfig_();
  if (!cfg.url || cfg.mode === 'no') return;
  var embeds = [];
  news.forEach(function (n) {
    var row = siteRow_(n.id);
    if (!row) return;
    var name = row['Mineral'] + ' (' + credits_(row['Precio (Cr)']) + '/t)';
    if (n.isNew) embeds.push(siteEmbed_('⛏️ Nuevo sitio: ' + name, 0xff8a1f, row, d.cmdr));
    else if (Number(row['Máx taladros']) > n.prevRigs) embeds.push(siteEmbed_('🏆 Récord: ' + row['Máx taladros'] + ' taladros en ' + name, 0xffd166, row, d.cmdr));
    else if (cfg.mode === 'sesiones') embeds.push(siteEmbed_('🔁 Sesión en ' + name, 0x4fd1ff, row, d.cmdr));
  });
  if (!embeds.length) logDiscord_('sin aviso', d.system + ' · ' + d.body, news.length + ' sitio(s), ninguno nuevo ni récord' +
    (news.length ? '' : ' (la sesión no trae sitios)'));
  for (var i = 0; i < embeds.length; i += 10) sendDiscord_({ embeds: embeds.slice(i, i + 10) });
}

function notifyDiscovery_(d) {
  var cfg = discordConfig_();
  if (!cfg.url || cfg.mode === 'no') return;
  var raw = JSON.stringify(d.raw || {});
  sendDiscord_({ embeds: [{
    title: '🆕 Novedad en el journal: ' + d.event, color: 0x4fd1ff, url: WEB_URL,
    description: 'El plugin ha visto algo que no conocía. Puede ser el evento oficial de minería en superficie.\n```json\n' +
      raw.slice(0, 1500) + (raw.length > 1500 ? '…' : '') + '\n```',
    footer: { text: 'Pestaña Eventos de la hoja · Skull Mining' }
  }] });
}

function notifyState_(d, label, siteId, esName) {
  var cfg = discordConfig_();
  if (!cfg.url || cfg.mode === 'no' || !cfg.states || d.state !== 'agotado' || !siteId) return;
  var row = siteRow_(siteId);
  if (row) sendDiscord_({ embeds: [siteEmbed_('🚫 Agotado: ' + row['Mineral'], 0xff5d5d, row, d.cmdr)] });
}

// Aviso de un sitio que estaba agotado y alguien ha visto con mineral otra vez (mismo interruptor que el de agotado)
function notifyRegen_(g) {
  var cfg = discordConfig_();
  if (!cfg.url || cfg.mode === 'no' || !cfg.states) return;
  var row = siteRow_(g.siteId);
  if (!row) return;
  var emb = siteEmbed_('♻ Regenerado: ' + row['Mineral'], 0x4ade80, row, g.cmdr);
  emb.description += '\n♻ Estuvo agotado entre ' + g.minDays + ' y ' + g.maxDays + ' días.';
  sendDiscord_({ embeds: [emb] });
}

// Ejecuta esta función desde el editor para comprobar que el webhook funciona
function probarDiscord() {
  var ok = sendDiscord_({ content: '✅ Skull Mining conectado a este canal. Aquí llegarán los sitios nuevos y los récords de la flota: ' + WEB_URL });
  Logger.log(ok ? 'Mensaje enviado a Discord' : 'No se pudo enviar: revisa DISCORD_WEBHOOK en Propiedades del script');
}

// Distancia de cada sitio al más cercano del mismo cuerpo (datos de toda la flota)
function recomputeNearest_(system, body, R) {
  if (!R) return;
  var sh = sheet_('Sitios');
  var H = HEADERS['Sitios'];
  var values = sh.getDataRange().getValues();
  var idx = [];
  for (var i = 1; i < values.length; i++) if (values[i][1] === system && values[i][2] === body) idx.push(i);
  var cLat = H.indexOf('Lat'), cLon = H.indexOf('Lon'), cMin = H.indexOf('Nombre interno');
  idx.forEach(function (i) {
    var any = null, same = null;
    idx.forEach(function (j) {
      if (i === j) return;
      var dd = haversine_(values[i][cLat], values[i][cLon], values[j][cLat], values[j][cLon], R);
      if (any === null || dd < any) any = dd;
      if (values[i][cMin] === values[j][cMin] && (same === null || dd < same)) same = dd;
    });
    sh.getRange(i + 1, H.indexOf('Sitio más cercano (m)') + 1, 1, 2)
      .setValues([[any === null ? '' : Math.round(any), same === null ? '' : Math.round(same)]]);
  });
}

function esNames_() {
  var m = {};
  sheet_('Precios').getDataRange().getValues().slice(1).forEach(function (p) {
    if (p[0]) m[String(p[0]).toLowerCase()] = p[1] || p[0];
  });
  return m;
}

// ------------------------------------------------------------------------- otros
function handleSale_(d) {
  sheet_('Ventas').appendRow([d.time, d.cmdr, d.type, d.name, d.count, d.sell_price, d.total, d.system, d.market_id]);
}

function handleBody_(d) {
  var sh = sheet_('Cuerpos');
  var values = sh.getDataRange().getValues();
  var row = [d.system, d.body, d.planet_class || '', d.gravity_g || '', d.temp_k || '', d.radius_m || '',
             d.atmosphere || '', d.dist_ls || '', nz_(d.mining_locations), d.signals ? JSON.stringify(d.signals) : '',
             new Date(), d.cmdr || ''];
  var cV = values[0].indexOf('Vulcanismo') + 1, volc = volcanismText_(d.volcanism);
  for (var i = 1; i < values.length; i++) {
    if (values[i][0] === d.system && values[i][1] === d.body) {
      // no pisar datos buenos con vacíos
      for (var c = 0; c < row.length; c++) if (row[c] === '' || row[c] === null) row[c] = values[i][c];
      sh.getRange(i + 1, 1, 1, row.length).setValues([row]);
      if (cV && volc) sh.getRange(i + 1, cV).setValue(volc);
      return;
    }
  }
  sh.appendRow(row);
  if (cV && volc) sh.getRange(sh.getLastRow(), cV).setValue(volc);
}

function handleEvent_(d) {
  var sh = sheet_('Eventos');
  var seen = sh.getLastRow() > 1 && sh.getRange(2, 3, sh.getLastRow() - 1, 1).getValues()
    .some(function (r) { return r[0] === d.event; });
  sh.appendRow([d.time, d.cmdr, d.event, d.system, d.body, d.lat, d.lon,
                JSON.stringify(d.raw || {}).slice(0, 45000)]);
  // Primera vez que aparece: probablemente Frontier ha añadido datos nuevos de minería
  if (!seen) { try { notifyDiscovery_(d); } catch (err) { Logger.log('Discord: ' + err); } }
}

function priceMap_() {
  var v = sheet_('Precios').getDataRange().getValues().slice(1);
  var m = {};
  v.forEach(function (r) {
    var p = Number(r[3]) || 0;
    [r[0], r[1], r[2]].forEach(function (k) { if (k) m[String(k).toLowerCase()] = p; });
  });
  return m;
}

function ensurePrices_(tonnesByType, names, prices) {
  var sh = sheet_('Precios');
  Object.keys(tonnesByType).forEach(function (t) {
    var key = t.toLowerCase();
    var name = String(names[t] || '').toLowerCase();
    if (prices[key] === undefined && prices[name] !== undefined) {
      prices[key] = prices[name];
      // anotar el nombre interno real en la fila que coincide por nombre
      var v = sh.getDataRange().getValues();
      for (var i = 1; i < v.length; i++) {
        if (String(v[i][1]).toLowerCase() === name || String(v[i][2]).toLowerCase() === name) {
          sh.getRange(i + 1, 1).setValue(key);
          sh.getRange(i + 1, 5).setValue('sí');
          break;
        }
      }
    } else if (prices[key] === undefined) {
      sh.appendRow([key, names[t] || '', '', '', 'sí (nuevo, falta precio)']);
      prices[key] = 0;
    } else {
      var v2 = sh.getDataRange().getValues();
      for (var j = 1; j < v2.length; j++) {
        if (String(v2[j][0]).toLowerCase() === key && v2[j][4] !== 'sí') { sh.getRange(j + 1, 5).setValue('sí'); break; }
      }
    }
  });
}

// ------------------------------------------------------------------ dónde vender
// Mejores estaciones cerca de un sistema que compran un mineral, según Spansh (datos de EDDN, los
// mismos que usa Inara; Inara no tiene API de mercados). Se guarda en caché 3 h por mineral y sistema.
var SELL_MAX_LY = 80;
var SELL_CACHE_S = 3 * 3600;
var SELL_MIN_DEMAND = 50;      // menos demanda no compensa el viaje
var SELL_MAX_AGE_DAYS = 30;    // precios más viejos no son fiables (prueba real 1-oct-2026: había datos de 2024)

function sellPlaces_(mineral, system) {
  mineral = String(mineral || '').trim(); system = String(system || '').trim();
  if (!mineral || !system || mineral.length > 60 || system.length > 80) return { ok: false, error: 'params' };
  var key = ('sell2|' + mineral + '|' + system).toLowerCase().slice(0, 240);
  var cache = CacheService.getScriptCache();
  var hit = cache.get(key);
  if (hit) return JSON.parse(hit);
  var out;
  try {
    out = { ok: true, mineral: mineral, system: system, maxLy: SELL_MAX_LY, results: spanshSellSearch_(mineral, system),
            fetched: new Date().toISOString() };
  } catch (err) {
    return { ok: false, error: String(err).slice(0, 200) };
  }
  try { cache.put(key, JSON.stringify(out), SELL_CACHE_S); } catch (e) { /* demasiado grande: sin caché */ }
  return out;
}

function spanshSellSearch_(mineral, system) {
  var filter = { name: mineral, sell_price: { value: [1, 999999999], comparison: '<=>' },
                 demand: { value: [SELL_MIN_DEMAND, 999999999], comparison: '<=>' } };
  var base = { filters: { market: [filter], distance: { min: 0, max: SELL_MAX_LY } },
               size: 100, page: 0, reference_system: system };
  var withSort = JSON.parse(JSON.stringify(base));
  withSort.sort = [{ market_sell_price: [{ name: mineral, direction: 'desc' }] }];
  var data = spanshPost_('/stations/search', withSort) || spanshPost_('/stations/search', base);
  if (!data || !data.results) throw new Error('Spansh no respondió');
  var rows = [];
  data.results.forEach(function (st) {
    if (/carrier/i.test(String(st.type || ''))) return;  // las naves nodriza cambian de sitio y de precio
    var m = (st.market || []).filter(function (c) { return String(c.commodity || '').toLowerCase() === mineral.toLowerCase(); })[0];
    if (!m || !m.sell_price) return;
    rows.push({ station: st.name, system: st.system_name, ly: st.distance != null ? Math.round(st.distance * 10) / 10 : null,
                ls: st.distance_to_arrival != null ? Math.round(st.distance_to_arrival) : null,
                price: m.sell_price, demand: m.demand, large: !!st.has_large_pad, planetary: !!st.is_planetary,
                updated: st.market_updated_at || st.updated_at || '', marketId: st.market_id || null });
  });
  rows.sort(function (a, b) { return b.price - a.price || (a.ly || 0) - (b.ly || 0); });
  // Primero los datos recientes; si hay pocos, se completan con los viejos (la web los marca)
  var limit = Date.now() - SELL_MAX_AGE_DAYS * 86400000;
  rows.forEach(function (r) { r.stale = !r.updated || timeOf_(r.updated) < limit; });
  var fresh = rows.filter(function (r) { return !r.stale; });
  return fresh.length >= 3 ? fresh.slice(0, 8) : fresh.concat(rows.filter(function (r) { return r.stale; })).slice(0, 8);
}

function spanshPost_(path, body) {
  var res = UrlFetchApp.fetch('https://spansh.co.uk/api' + path, {
    method: 'post', contentType: 'application/json', payload: JSON.stringify(body), muteHttpExceptions: true,
    headers: { 'User-Agent': 'SkullMining (Google Apps Script; github.com/skullflota/SkullMining)' }
  });
  if (res.getResponseCode() !== 200) { Logger.log('Spansh ' + res.getResponseCode() + ': ' + res.getContentText().slice(0, 300)); return null; }
  try { return JSON.parse(res.getContentText()); } catch (e) { return null; }
}

// ------------------------------------------------------------- vulcanismo (Spansh)
// "No volcanism" → "ninguno"; el resto en minúsculas tal cual (p. ej. "major rocky magma volcanism").
function volcanismText_(v) {
  v = String(v || '').trim().toLowerCase();
  if (!v) return '';
  if (v === 'no volcanism' || v === 'none' || v === 'ninguno') return 'ninguno';
  return v.indexOf('volcanism') >= 0 ? v : v + ' volcanism';
}

// Rellena vulcanismo (y tipo de planeta si falta) de un cuerpo con los datos públicos de Spansh.
// force=false: solo si la fila no lo tiene. Devuelve true si escribió algo.
function fillBodyFromSpansh_(system, body, force) {
  var sh = sheet_('Cuerpos');
  var v = sh.getDataRange().getValues();
  var H = v[0], cV = H.indexOf('Vulcanismo') + 1, cP = H.indexOf('Tipo planeta') + 1;
  if (!cV) { ensureSchema_(true); return fillBodyFromSpansh_(system, body, force); }
  var row = -1;
  for (var i = 1; i < v.length; i++) if (v[i][0] === system && v[i][1] === body) { row = i + 1; break; }
  if (row < 0 || (!force && v[row - 1][cV - 1])) return false;
  var bodies = spanshBodies_(system);
  var b = bodies && bodies.filter(function (x) { return String(x.name).toLowerCase() === String(body).toLowerCase(); })[0];
  if (!b) return false;
  var volc = volcanismText_(b.volcanismType || 'No volcanism');
  sh.getRange(row, cV).setValue(volc);
  if (!v[row - 1][cP - 1] && b.subType) sh.getRange(row, cP).setValue(String(b.subType).replace(/ world$/, ' body'));
  return true;
}

function spanshBodies_(system) {
  var cache = CacheService.getScriptCache(), key = ('bodies|' + system).toLowerCase().slice(0, 240);
  var hit = cache.get(key);
  if (hit) return JSON.parse(hit);
  var found = spanshPost_('/systems/search', { filters: { name: { value: system } }, size: 1, page: 0 });
  var sys = found && found.results && found.results.filter(function (x) {
    return String(x.name || '').toLowerCase() === String(system).toLowerCase(); })[0];
  if (!sys || !sys.id64) return null;
  var res = UrlFetchApp.fetch('https://spansh.co.uk/api/dump/' + sys.id64, { muteHttpExceptions: true,
    headers: { 'User-Agent': 'SkullMining (Google Apps Script; github.com/skullflota/SkullMining)' } });
  if (res.getResponseCode() !== 200) return null;
  var dump = JSON.parse(res.getContentText());
  var out = ((dump.system || {}).bodies || []).filter(function (x) { return x.type === 'Planet'; })
    .map(function (x) { return { name: x.name, subType: x.subType || '', volcanismType: x.volcanismType || '' }; });
  try { cache.put(key, JSON.stringify(out), 6 * 3600); } catch (e) { /* demasiado grande */ }
  return out;
}

// Ejecutar a mano una vez: rellena el vulcanismo de todos los cuerpos que no lo tengan
function rellenarVulcanismo() {
  var v = sheet_('Cuerpos').getDataRange().getValues();
  var n = 0, fail = [];
  for (var i = 1; i < v.length; i++) {
    if (!v[i][0] || !v[i][1]) continue;
    try { if (fillBodyFromSpansh_(v[i][0], v[i][1], false)) n++; } catch (e) { fail.push(v[i][1] + ' (' + e + ')'); }
  }
  Logger.log('Cuerpos actualizados: ' + n + (fail.length ? ' · errores: ' + fail.slice(0, 5).join(' | ') : ''));
}

// Diagnóstico paso a paso con un cuerpo conocido
function probarVulcanismo() {
  var system = 'Pegasi Sector JN-S b4-7', body = 'Pegasi Sector JN-S b4-7 B 4 a';
  var found = spanshPost_('/systems/search', { filters: { name: { value: system } }, size: 1, page: 0 });
  Logger.log('1) búsqueda de sistema: ' + JSON.stringify(found && found.results && found.results.slice(0, 1)).slice(0, 600));
  var sys = found && found.results && found.results[0];
  if (!sys) return;
  var res = UrlFetchApp.fetch('https://spansh.co.uk/api/dump/' + sys.id64, { muteHttpExceptions: true });
  Logger.log('2) dump: código ' + res.getResponseCode() + ', ' + res.getContentText().length + ' caracteres');
  var dump = JSON.parse(res.getContentText());
  var b = ((dump.system || {}).bodies || []).filter(function (x) { return x.name === body; })[0];
  Logger.log('3) cuerpo: ' + JSON.stringify(b ? { name: b.name, type: b.type, subType: b.subType, volcanismType: b.volcanismType } : null));
  Logger.log('4) claves del cuerpo: ' + (b ? Object.keys(b).join(', ') : '-'));
}

// Ejecutar a mano desde el editor para comprobar que Spansh responde
function probarSpansh() {
  var r = sellPlaces_('Monazite', 'Pegasi Sector JN-S b4-7');
  Logger.log(JSON.stringify(r, null, 1).slice(0, 3000));
}

// --------------------------------------------------------------------- utilidades
function sheet_(name) {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
  if (!sh) { setup(); sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name); }
  return sh;
}

function findRow_(name, col, value) {
  var v = sheet_(name).getRange(1, col, sheet_(name).getLastRow(), 1).getValues();
  for (var i = 1; i < v.length; i++) if (v[i][0] === value) return i + 1;
  return -1;
}

function haversine_(lat1, lon1, lat2, lon2, R) {
  var toR = Math.PI / 180;
  var dp = (lat2 - lat1) * toR, dl = (lon2 - lon1) * toR;
  var a = Math.pow(Math.sin(dp / 2), 2) + Math.cos(lat1 * toR) * Math.cos(lat2 * toR) * Math.pow(Math.sin(dl / 2), 2);
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

function timeOf_(x) { return x instanceof Date ? x.getTime() : (Date.parse(x) || 0); }
function round_(x, n) { var f = Math.pow(10, n); return Math.round(x * f) / f; }
function nz_(x) { return x === null || x === undefined ? '' : x; }
function jsonp_(o, callback) {
  var txt = JSON.stringify(o);
  if (callback && /^[A-Za-z_$][\w$.]{0,60}$/.test(callback)) {
    return ContentService.createTextOutput(callback + '(' + txt + ');').setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService.createTextOutput(txt).setMimeType(ContentService.MimeType.JSON);
}

function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
