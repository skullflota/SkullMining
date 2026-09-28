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

var SITE_MATCH_M = 60;     // un sitio (un solo mineral) mide ~50 m como mucho
var ZONE_RADIUS_M = 10000; // zonas de varios km (más grandes en planetas grandes); se asigna la más cercana
var TRACK_CHUNK = 45000;   // límite práctico por celda
var SCHEMA_VERSION = '6';  // sube cuando se añaden columnas o pestañas
var WEB_URL = 'https://skullflota.github.io/SkullMining/';
// Alto/Medio/Bajo es la DENSIDAD del sitio (fija, la genera el juego). Agotado es aparte:
// el desgaste lo comparten todos los jugadores y un sitio agotado no se regenera.
var STATE_LABELS = { alto: 'Alta', medio: 'Media', bajo: 'Baja', agotado: 'Agotado' };
var OLD_DENSITY = { 'Alto': 'Alta', 'Medio': 'Media', 'Bajo': 'Baja' };

var HEADERS = {
  'Sitios': ['SiteID', 'Sistema', 'Cuerpo', 'Mineral', 'Nombre interno', 'Precio (Cr)', 'Lat', 'Lon',
             'Máx plataformas', 'Dist. mín entre plataformas (m)', 'Extensión (m)', 'T/recogida',
             'Valor por vuelta (Cr)', 'Visitas', 'Recogidas', 'Toneladas totales', 'Sitio más cercano (m)',
             'Mismo mineral más cercano (m)', 'Terreno zona', 'Vel. efectiva zona (m/s)', 'Señal zona',
             'Sitios minería en cuerpo', 'Tipo planeta', 'Gravedad (g)', 'Temp (K)', 'Última visita', 'Último CMDR',
             'Zona', 'Densidad', 'Densidad fecha', 'Densidad CMDR', 'Agotado', 'Agotado CMDR'],
  'Visitas': ['SessionID', 'SiteID', 'Fecha', 'CMDR', 'Mineral', 'Plataformas', 'Dist. mín entre plataformas (m)',
              'Extensión (m)', 'Recogidas', 'Toneladas', 'T/recogida', 'Terreno zona', 'Vel. efectiva zona (m/s)',
              'Zona'],
  'Sesiones': ['SessionID', 'Sitios', 'Recibido', 'CMDR', 'Sistema', 'Cuerpo', 'Inicio', 'Fin', 'Duración (min)',
               'Plataformas', 'Recogidas', 'T/recogida', 'Ciclo recogida (min)', 'Señal zona',
               'Sitios minería en cuerpo', 'Materiales', 'Cargas a nave (t)', 'Toneladas', 'Valor estimado (Cr)',
               'Cr/h', 'Ruta recogida (m)', 'Vel. efectiva (m/s)', 'Vel. en movimiento (m/s)', 'Sinuosidad',
               'Terreno', 'Recorrido (m)', 'Minerales', 'Tipo planeta', 'Gravedad (g)', 'Temp (K)', 'Radio (m)',
               'Vehículo', 'Motivo cierre', 'Eventos desconocidos', 'Versión plugin', 'Zonas'],
  'Plataformas': ['SessionID', 'SiteID', 'Nº', 'Lat', 'Lon', 'Mineral', 'Toneladas', 'Recogidas', 'T/recogida',
                  'Primera', 'Última'],
  'Tramos': ['SessionID', 'De', 'A', 'Línea recta (m)', 'Recorrido (m)', 'Tiempo (s)',
             'Vel. efectiva (m/s)', 'Sinuosidad'],
  'Recorridos': ['SessionID', 'Parte', 'Datos (t,lat,lon,alt;...)'],
  // Datos en bruto de cada tonelada (plugin 0.5.0+). Las partes se concatenan en orden.
  'Recogidas': ['SessionID', 'Inicio (epoch s)', 'Parte', 'Datos (décimas de s,tipo,lat,lon,zona;...)'],
  'Cuerpos': ['Sistema', 'Cuerpo', 'Tipo planeta', 'Gravedad (g)', 'Temp (K)', 'Radio (m)', 'Atmósfera',
              'Distancia (ls)', 'Sitios de minería', 'Señales', 'Actualizado', 'CMDR'],
  'Ventas': ['Fecha', 'CMDR', 'Tipo', 'Nombre', 'Cantidad', 'Precio venta', 'Total', 'Sistema', 'MarketID'],
  'Eventos': ['Fecha', 'CMDR', 'Evento', 'Sistema', 'Cuerpo', 'Lat', 'Lon', 'JSON'],
  'Precios': ['Tipo (interno)', 'Nombre ES', 'Nombre EN', 'Precio medio (Cr)', 'Interno verificado'],
  // Zonas de minería (señales "Planetary Mining Location Signal (N)"). La columna de minerales
  // se rellena a mano: el juego solo muestra esa lista en pantalla al fijar la zona.
  'Zonas': ['Sistema', 'Cuerpo', 'Zona', 'Lat', 'Lon', 'Minerales (anotar a mano)', 'Minerales confirmados',
            'Sitios', 'Mejor valor por vuelta (Cr)', 'Actualizado'],
  'Estados': ['Fecha', 'CMDR', 'Sistema', 'Cuerpo', 'Zona', 'Lat', 'Lon', 'Mineral', 'Estado', 'SiteID']
};

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
    if (have.length < want.length) {
      var extra = want.slice(have.length);
      sh.getRange(1, have.length + 1, 1, extra.length).setValues([extra]).setFontWeight('bold').setBackground('#fff2cc');
    }
  });
  if (migrateStates) recomputeAllStates_();
  props.setProperty('SCHEMA_VERSION', SCHEMA_VERSION);
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
      default: return json_({ ok: false, error: 'kind' });
    }
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
  return json_({ ok: true });
}

// Lectura de sitios para el futuro visor: ?token=...&sheet=Sitios
function doGet(e) {
  var p = (e && e.parameter) || {};
  // Lectura pública para la web del ranking: solo sitios, sin nombres de comandante
  if (p.view === 'ranking') { ensureSchema_(false); return publicRanking_(p.callback); }
  var token = PropertiesService.getScriptProperties().getProperty('FLEET_TOKEN');
  if (!e || !e.parameter || e.parameter.token !== token) return json_({ ok: false, error: 'token' });
  var name = e.parameter.sheet || 'Sitios';
  if (['Sitios', 'Visitas', 'Sesiones', 'Plataformas', 'Tramos', 'Precios', 'Zonas', 'Estados'].indexOf(name) < 0) return json_({ ok: false, error: 'sheet' });
  var values = sheet_(name).getDataRange().getValues();
  var head = values.shift();
  var rows = values.map(function (r) { var o = {}; head.forEach(function (h, i) { o[h] = r[i]; }); return o; });
  return json_({ ok: true, rows: rows });
}

var PUBLIC_SITE_FIELDS = {
  'SiteID': 'id', 'Sistema': 'system', 'Cuerpo': 'body', 'Mineral': 'mineral', 'Nombre interno': 'type',
  'Precio (Cr)': 'price', 'Lat': 'lat', 'Lon': 'lon', 'Máx plataformas': 'rigs',
  'Dist. mín entre plataformas (m)': 'rigSpacing', 'Extensión (m)': 'extent', 'T/recogida': 'tpc',
  'Valor por vuelta (Cr)': 'value', 'Visitas': 'visits', 'Recogidas': 'collections',
  'Toneladas totales': 'tonnes', 'Sitio más cercano (m)': 'nearest', 'Mismo mineral más cercano (m)': 'nearestSame',
  'Terreno zona': 'terrain', 'Vel. efectiva zona (m/s)': 'speed', 'Señal zona': 'signal',
  'Sitios minería en cuerpo': 'bodySites', 'Tipo planeta': 'planetClass', 'Gravedad (g)': 'gravity',
  'Temp (K)': 'temp', 'Última visita': 'lastVisit', 'Zona': 'zone', 'Densidad': 'density',
  'Densidad fecha': 'densityTime', 'Agotado': 'depleted'
};

function publicRanking_(callback) {
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
  var out = { ok: true, updated: new Date().toISOString(), sites: sites, zones: zones,
              stats: { sites: sites.length, sessions: ses.length, commanders: Object.keys(cmdrs).length, tonnes: tonnes } };
  var txt = JSON.stringify(out);
  if (callback && /^[A-Za-z_$][\w$.]{0,60}$/.test(callback)) {
    return ContentService.createTextOutput(callback + '(' + txt + ');').setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService.createTextOutput(txt).setMimeType(ContentService.MimeType.JSON);
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

  // Sitios: uno por grupo de plataformas del mismo mineral
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

  var pl = sheet_('Plataformas');
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
                            mining_locations: d.mining_locations_on_body, cmdr: d.cmdr });
  ids.forEach(function (id) { recomputeSite_(id, prices); });
  recomputeNearest_(d.system, d.body, d.planet_radius_m);
  recomputeZones_(d.system, d.body);
  try { notifySession_(d, news, esName, prices); } catch (err) { Logger.log('Discord: ' + err); }
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
      return { rigs: Number(row[H.indexOf('Máx plataformas')]) || 0 };
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
  set('Gravedad (g)', d.gravity_g); set('Temp (K)', d.temp_k); set('Zona', st.zone);
  sh.appendRow(row);
  applyPendingStates_(id, d.system, d.body, st.main_type, st.lat, st.lon, d.planet_radius_m);
  return id;
}

function recomputeSite_(siteId, prices) {
  var vis = sheet_('Visitas').getDataRange().getValues();
  var VH = vis[0];
  var vc = function (n) { return VH.indexOf(n); };
  var rows = vis.slice(1).filter(function (r) { return r[1] === siteId; });
  if (!rows.length) return;
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
  var maxRigs = Math.max.apply(null, vals('Plataformas').concat([0]));
  var spacing = vals('Dist. mín entre plataformas (m)');
  var tpc = median(vals('T/recogida'));
  var votes = {};
  vals('Terreno zona').forEach(function (t) { if (t !== 'sin datos') votes[t] = (votes[t] || 0) + 1; });

  set('Precio (Cr)', price);
  set('Máx plataformas', maxRigs);
  set('Dist. mín entre plataformas (m)', spacing.length ? Math.min.apply(null, spacing) : '');
  set('Extensión (m)', Math.max.apply(null, vals('Extensión (m)').concat([0])));
  set('T/recogida', tpc);
  // Valor de recoger todas las plataformas una vez: la cifra para comparar sitios
  set('Valor por vuelta (Cr)', tpc !== '' ? Math.round(maxRigs * tpc * price) : '');
  set('Visitas', rows.length);
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

// ----------------------------------------------------------------------- estados
function handleState_(d) {
  var label = STATE_LABELS[d.state];
  if (!label) return;
  var esName = esNames_();
  var siteId = findSiteNear_(d.system, d.body, d.type, d.lat, d.lon, d.planet_radius_m);
  sheet_('Estados').appendRow([d.time, d.cmdr, d.system, d.body, nz_(d.zone), d.lat, d.lon,
                               d.type ? (esName[d.type] || d.type) : '', label, siteId || '']);
  if (siteId) setSiteState_(siteId, label, d.time, d.cmdr);
  if (d.zone !== null && d.zone !== undefined) upsertZone_(d.system, d.body, d.zone);
  try { notifyState_(d, label, siteId, esName); } catch (err) { Logger.log('Discord: ' + err); }
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
function setSiteState_(siteId, label, when, cmdr) {
  var sh = sheet_('Sitios');
  var H = HEADERS['Sitios'];
  var r = findRow_('Sitios', 1, siteId);
  if (r < 0) return;
  if (label === 'Agotado') {
    sh.getRange(r, H.indexOf('Agotado') + 1, 1, 2).setValues([[when, cmdr || '']]);
  } else {
    sh.getRange(r, H.indexOf('Densidad') + 1, 1, 3).setValues([[OLD_DENSITY[label] || label, when, cmdr || '']]);
    sh.getRange(r, H.indexOf('Agotado') + 1, 1, 2).setValues([['', '']]);
  }
}

// Recalcula densidad y agotado de un sitio (o de todos) a partir del historial de la pestaña Estados.
function recomputeSiteStates_(siteId) {
  var v = sheet_('Estados').getDataRange().getValues().slice(1)
    .filter(function (r) { return r[9] && (!siteId || r[9] === siteId); })
    .sort(function (a, b) { return timeOf_(a[0]) - timeOf_(b[0]); });
  var seen = {};
  v.forEach(function (r) { seen[r[9]] = 1; setSiteState_(r[9], r[8], r[0], r[1]); });
  return seen;
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
//   DISCORD_MODE    = novedades (sitio nuevo o récord de plataformas) | sesiones | no
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
  return res.getResponseCode() < 300;
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
      { name: 'Plataformas', value: String(row['Máx plataformas'] || 0), inline: true },
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
    else if (Number(row['Máx plataformas']) > n.prevRigs) embeds.push(siteEmbed_('🏆 Récord: ' + row['Máx plataformas'] + ' plataformas en ' + name, 0xffd166, row, d.cmdr));
    else if (cfg.mode === 'sesiones') embeds.push(siteEmbed_('🔁 Sesión en ' + name, 0x4fd1ff, row, d.cmdr));
  });
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
  for (var i = 1; i < values.length; i++) {
    if (values[i][0] === d.system && values[i][1] === d.body) {
      // no pisar datos buenos con vacíos
      for (var c = 0; c < row.length; c++) if (row[c] === '' || row[c] === null) row[c] = values[i][c];
      sh.getRange(i + 1, 1, 1, row.length).setValues([row]);
      return;
    }
  }
  sh.appendRow(row);
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
function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
