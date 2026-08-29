"use strict";

const formulario = document.querySelector("#formulario-filtros");
const botonAplicar = document.querySelector("#aplicar-filtros");
const botonLimpiar = document.querySelector("#limpiar-filtros");
const estadoConsulta = document.querySelector("#estado-consulta");
const avisoCalidad = document.querySelector("#aviso-calidad");
const dashboard = document.querySelector("#dashboard");
const graficos = document.querySelector("#graficos");
const sinResultados = document.querySelector("#sin-resultados");
const instanciasGraficos = new Map();
const formatoNumero = new Intl.NumberFormat("es-ES");

formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    cargarEstadisticas();
});

botonLimpiar.addEventListener("click", () => {
    formulario.reset();
    cargarEstadisticas();
});

document.addEventListener("DOMContentLoaded", () => cargarEstadisticas());

async function cargarEstadisticas() {
    cambiarEstadoCarga(true);
    const parametros = new URLSearchParams();
    new FormData(formulario).forEach((valor, clave) => {
        if (String(valor).trim()) parametros.set(clave, valor);
    });
    const url = parametros.size ? `/api/estadisticas?${parametros}` : "/api/estadisticas";

    try {
        const respuesta = await fetch(url, {headers: {Accept: "application/json"}});
        const datos = await respuesta.json();
        if (!respuesta.ok) {
            const mensaje = respuesta.status === 503
                ? "El archivo Excel no está disponible temporalmente. Inténtalo de nuevo más tarde."
                : datos.error || "No se ha podido completar la consulta.";
            throw new Error(mensaje);
        }
        actualizarDashboard(datos);
    } catch (error) {
        mostrarError(error.message || "No se ha podido conectar con la API.");
    } finally {
        cambiarEstadoCarga(false);
    }
}

function cambiarEstadoCarga(cargando) {
    botonAplicar.disabled = cargando;
    botonLimpiar.disabled = cargando;
    if (cargando) {
        estadoConsulta.textContent = "Cargando datos...";
        estadoConsulta.className = "estado estado-cargando";
        estadoConsulta.hidden = false;
    } else if (estadoConsulta.classList.contains("estado-cargando")) {
        estadoConsulta.hidden = true;
    }
}

function mostrarError(mensaje) {
    estadoConsulta.textContent = mensaje;
    estadoConsulta.className = "estado estado-error";
    estadoConsulta.hidden = false;
    avisoCalidad.hidden = true;
    dashboard.hidden = true;
}

function actualizarDashboard(datos) {
    estadoConsulta.hidden = true;
    dashboard.hidden = false;
    actualizarOpciones(datos.opciones, datos.filtros);
    document.querySelector("#total-plazas").textContent = formatoNumero.format(datos.resumen.total_plazas);
    document.querySelector("#total-registros").textContent = formatoNumero.format(datos.resumen.total_registros);
    document.querySelector("#total-provincias").textContent = formatoNumero.format(datos.resumen.total_provincias);
    document.querySelector("#total-administraciones").textContent = formatoNumero.format(datos.resumen.total_administraciones);
    actualizarMetadatos(datos);
    actualizarAvisoCalidad(datos.calidad_datos);

    const vacio = datos.resumen.total_registros === 0;
    sinResultados.hidden = !vacio;
    graficos.hidden = vacio;
    if (vacio) {
        destruirGraficos();
        return;
    }

    actualizarGraficos(datos);
}

function actualizarGraficos(datos) {
    renderizarRanking("ranking-administraciones", datos.top_administraciones, "administracion", 5);
    renderizarRanking("ranking-puestos", datos.top_puestos, "puesto", 10);
    crearGraficoProvincias(datos.plazas_por_provincia);
    crearGraficoEvolucion(datos.evolucion_mensual);
}

function actualizarOpciones(opciones, filtros) {
    [
        ["provincia", opciones.provincias, filtros.provincia],
        ["sistema", opciones.sistemas, filtros.sistema],
        ["turno", opciones.turnos, filtros.turno],
    ].forEach(([id, valores, seleccionado]) => {
        const desplegable = document.querySelector(`#${id}`);
        desplegable.replaceChildren(new Option("Todas", ""));
        valores.forEach((valor) => desplegable.add(new Option(valor, valor)));
        desplegable.value = seleccionado || "";
    });
}

function actualizarMetadatos(datos) {
    const actualizacion = datos.archivo.ultima_modificacion
        ? new Date(datos.archivo.ultima_modificacion).toLocaleString("es-ES")
        : "no disponible";
    document.querySelector("#ultima-actualizacion").textContent = `Última actualización: ${actualizacion}`;

    const filtros = [];
    if (datos.filtros.fecha_inicio || datos.filtros.fecha_final) {
        filtros.push(`Fechas: ${datos.filtros.fecha_inicio || "inicio"} — ${datos.filtros.fecha_final || "hoy"}`);
    }
    if (datos.filtros.puesto) filtros.push(`Puesto: ${datos.filtros.puesto}`);
    if (datos.filtros.provincia) filtros.push(`Provincia: ${datos.filtros.provincia}`);
    if (datos.filtros.sistema) filtros.push(`Sistema: ${datos.filtros.sistema}`);
    if (datos.filtros.turno) filtros.push(`Turno: ${datos.filtros.turno}`);
    document.querySelector("#filtros-activos").textContent = filtros.length ? filtros.join(" · ") : "Sin filtros aplicados";
}

function actualizarAvisoCalidad(calidad) {
    const incidencias = calidad.fechas_invalidas + calidad.numeros_plazas_invalidos;
    avisoCalidad.hidden = incidencias === 0;
    if (incidencias) {
        avisoCalidad.textContent = `${formatoNumero.format(incidencias)} incidencias en registros históricos contienen datos que no han podido utilizarse completamente en las estadísticas.`;
    }
}

function prepararRanking(registros, claveTexto, limite) {
    const ordenados = [...registros].sort(
        (primero, segundo) => Number(segundo.plazas) - Number(primero.plazas)
    );
    const seleccionados = ordenados.slice(0, limite);
    const maximo = Math.max(0, ...seleccionados.map((registro) => Number(registro.plazas)));
    return seleccionados.map((registro) => {
        const valor = Number(registro.plazas);
        return {
            nombre: String(registro[claveTexto]),
            valor,
            porcentaje: maximo > 0 ? Math.max(0, valor / maximo * 100) : 0,
        };
    });
}

function renderizarRanking(idContenedor, registros, claveTexto, limite) {
    const contenedor = document.querySelector(`#${idContenedor}`);
    const filas = prepararRanking(registros, claveTexto, limite);
    contenedor.replaceChildren();
    if (!filas.length) {
        const vacio = document.createElement("p");
        vacio.className = "ranking-vacio";
        vacio.textContent = "Sin resultados";
        contenedor.append(vacio);
        return;
    }

    filas.forEach((fila) => {
        const elemento = document.createElement("article");
        elemento.className = "ranking-fila";
        const nombre = document.createElement("p");
        nombre.className = "ranking-nombre";
        nombre.textContent = fila.nombre;
        const medida = document.createElement("div");
        medida.className = "ranking-medida";
        const pista = document.createElement("div");
        pista.className = "ranking-pista";
        const barra = document.createElement("span");
        barra.className = "ranking-barra";
        barra.style.width = `${fila.porcentaje}%`;
        barra.setAttribute("role", "progressbar");
        barra.setAttribute("aria-valuenow", String(fila.valor));
        barra.setAttribute("aria-valuemin", "0");
        barra.setAttribute("aria-valuemax", String(Math.max(...filas.map((item) => item.valor))));
        const valor = document.createElement("strong");
        valor.className = "ranking-valor";
        valor.textContent = formatoNumero.format(fila.valor);
        pista.append(barra);
        medida.append(pista, valor);
        elemento.append(nombre, medida);
        contenedor.append(elemento);
    });
}

function crearGraficoProvincias(datos) {
    reemplazarGrafico("provincias", "grafico-provincias", {
        type: "bar",
        data: {labels: datos.map((fila) => fila.provincia), datasets: [{label: "Plazas", data: datos.map((fila) => fila.plazas), backgroundColor: "#5b82dc", borderColor: "#2457d6", borderWidth: 1, borderRadius: 5, maxBarThickness: 34}]},
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {padding: {top: 8}},
            plugins: {legend: {display: false}, tooltip: {callbacks: {label: etiquetaTooltip}}},
            scales: {x: {beginAtZero: true, ticks: {precision: 0}}, y: {beginAtZero: true, ticks: {precision: 0, autoSkip: true}}},
        },
    });
}

function crearGraficoEvolucion(datos) {
    reemplazarGrafico("evolucion", "grafico-evolucion", {
        type: "line",
        data: {labels: datos.map((fila) => fila.mes), datasets: [{label: "Plazas", data: datos.map((fila) => fila.plazas), borderColor: "#2457d6", backgroundColor: "rgba(36, 87, 214, .12)", borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, tension: .2, fill: true}]},
        options: {responsive: true, maintainAspectRatio: false, interaction: {intersect: false, mode: "index"}, plugins: {legend: {display: false}, valoresBarras: {mostrar: false}, tooltip: {callbacks: {label: etiquetaTooltip}}}, scales: {y: {beginAtZero: true, ticks: {precision: 0}}}},
    });
}

function reemplazarGrafico(clave, idCanvas, configuracion) {
    if (instanciasGraficos.has(clave)) {
        instanciasGraficos.get(clave).destroy();
        instanciasGraficos.delete(clave);
    }
    const canvas = document.querySelector(`#${idCanvas}`);
    canvas.removeAttribute("width");
    canvas.removeAttribute("height");
    canvas.style.width = "";
    canvas.style.height = "";
    const contexto = canvas.getContext("2d");
    instanciasGraficos.set(clave, new Chart(contexto, configuracion));
}

function destruirGraficos() {
    instanciasGraficos.forEach((grafico) => grafico.destroy());
    instanciasGraficos.clear();
}

function etiquetaTooltip(contexto) {
    const valor = contexto.parsed.x ?? contexto.parsed.y;
    return `Plazas: ${formatoNumero.format(valor)}`;
}
