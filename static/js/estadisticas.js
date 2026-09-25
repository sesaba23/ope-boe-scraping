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
let comparadoresSeleccionados = ["", "", "", "", ""];
const formatoNumero = new Intl.NumberFormat("es-ES");
const coloresComunidades = [
    "#f4a6a6", "#f7c59f", "#f9e79f", "#c8e6a0", "#9ed9c7",
    "#9fd8ef", "#a9b7ef", "#c7a8e8", "#e1a6d8", "#f3b3c3",
    "#f6c28b", "#d6e58d", "#8fd3c8", "#8fc7e8", "#a7a9e8",
    "#c9a5df", "#e5a9c8", "#f1b0a8", "#b8d99a", "#9ed7d2",
];

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
        if (String(valor).trim()) parametros.append(clave, valor);
    });
    comparadoresSeleccionados.forEach((valor) => { if (String(valor).trim()) parametros.append("comparar", valor); });
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
    actualizarSelectoresComparacion(datos.opciones.puestos || [], datos.filtros.puesto);
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
    crearGraficoEvolucionAnual(datos.evolucion_anual);
    crearGraficoMeses(datos.plazas_por_mes || []);
    const evolucion = datos.evolucion_anual_puestos || {years: [], series: []};
    crearGraficoPuestosAnual(evolucion);
    const estado = document.querySelector("#estado-comparacion-puestos");
    estado.textContent = evolucion.mode === "top5" ? "Mostrando los 5 puestos con más plazas" : evolucion.mode === "manual" ? `Comparando ${evolucion.series.length} puestos` : `Evolución de ${evolucion.series[0]?.label || "puesto seleccionado"}`;
    crearGraficoComunidades(datos.plazas_por_comunidad);
    crearGraficoProvincias(datos.plazas_por_provincia);
    renderizarRanking("distribucion-tipo-personal", datos.distribucion_tipo_personal || [], "tipo_personal", 7);
}

function actualizarSelectoresComparacion(opciones, principal) {
    comparadoresSeleccionados = comparadoresSeleccionados.map((valor) => valor === principal ? "" : valor);
    const ocupados = new Set(comparadoresSeleccionados.filter(Boolean));
    for (let indice = 0; indice < 5; indice += 1) {
        const select = document.querySelector(`#comparar_${indice + 1}`);
        select.replaceChildren(new Option("— Ninguno —", ""));
        opciones.forEach((valor) => {
            const option = new Option(valor, valor);
            option.disabled = valor === principal || (ocupados.has(valor) && valor !== comparadoresSeleccionados[indice]);
            select.add(option);
        });
        select.value = comparadoresSeleccionados[indice] || "";
        select.onchange = () => {
            comparadoresSeleccionados[indice] = select.value;
            const elegidos = comparadoresSeleccionados.filter(Boolean);
            if (new Set(elegidos).size !== elegidos.length || (principal && elegidos.includes(principal))) {
                comparadoresSeleccionados[indice] = "";
                select.value = "";
            }
            cargarEstadisticas();
        };
    }
}

function actualizarOpciones(opciones, filtros) {
    [
        ["provincia", opciones.provincias, filtros.provincia],
        ["ambito", opciones.ambitos || [], filtros.ambito],
        ["sistema", opciones.sistemas, filtros.sistema],
        ["turno", opciones.turnos, filtros.turno],
    ].forEach(([id, valores, seleccionado]) => {
        const desplegable = document.querySelector(`#${id}`);
        desplegable.replaceChildren(new Option("Todas", ""));
        valores.forEach((valor) => desplegable.add(new Option(valor, valor)));
        desplegable.value = seleccionado || "";
    });
    const contenedor = document.querySelector("#tipos-personal-filtros");
    const seleccionados = new Set(filtros.tipo_personal || []);
    contenedor.replaceChildren();
    (opciones.tipos_personal || []).forEach((valor) => {
        const etiqueta = document.createElement("label");
        const casilla = document.createElement("input");
        casilla.type = "checkbox";
        casilla.name = "tipo_personal";
        casilla.value = valor;
        casilla.checked = seleccionados.has(valor);
        etiqueta.append(casilla, ` ${valor}`);
        contenedor.append(etiqueta);
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
    if (datos.filtros.ambito) filtros.push(`Ámbito: ${datos.filtros.ambito}`);
    if (datos.filtros.sistema) filtros.push(`Sistema: ${datos.filtros.sistema}`);
    if (datos.filtros.turno) filtros.push(`Turno: ${datos.filtros.turno}`);
    if ((datos.filtros.tipo_personal || []).length) filtros.push(`Tipo de personal: ${datos.filtros.tipo_personal.join(", ")}`);
    document.querySelector("#filtros-activos").textContent = filtros.length ? filtros.join(" · ") : "Sin filtros aplicados";
}

function actualizarAvisoCalidad(calidad) {
    const descripciones = [
        ["fecha_no_utilizable", "sin fecha utilizable"],
        ["numero_plazas_no_utilizable", "sin número de plazas utilizable"],
        ["puesto_no_utilizable", "sin puesto utilizable"],
        ["provincia_no_disponible", "sin provincia disponible"],
        ["administracion_no_disponible", "sin administración disponible"],
        ["sistema_no_disponible", "sin sistema disponible"],
        ["turno_no_disponible", "sin turno disponible"],
    ];
    const visibles = descripciones.filter(([clave]) => Number(calidad[clave]) > 0);
    avisoCalidad.hidden = visibles.length === 0;
    const lista = document.querySelector("#lista-calidad");
    lista.replaceChildren();
    visibles.forEach(([clave, descripcion]) => {
        const elemento = document.createElement("li");
        const cantidad = Number(calidad[clave]);
        elemento.textContent = `${formatoNumero.format(cantidad)} ${cantidad === 1 ? "registro" : "registros"} ${descripcion}.`;
        lista.append(elemento);
    });
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

function crearGraficoEvolucionAnual(datos) {
    reemplazarGrafico("evolucion", "grafico-evolucion", {
        type: "bar",
        data: {labels: datos.map((fila) => String(fila.anio)), datasets: [{label: "Plazas", data: datos.map((fila) => fila.plazas), backgroundColor: "#5b82dc", borderColor: "#2457d6", borderWidth: 1, borderRadius: 5, maxBarThickness: 42}]},
        options: {responsive: true, maintainAspectRatio: false, plugins: {legend: {display: false}, tooltip: {callbacks: {title: tituloTooltipAnual, label: etiquetaTooltip}}}, scales: {x: {ticks: {precision: 0}}, y: {beginAtZero: true, ticks: {precision: 0}}}},
    });
}

function crearGraficoMeses(datos) {
    reemplazarGrafico("meses", "grafico-meses", {
        type: "bar",
        data: {labels: datos.map((fila) => fila.nombre), datasets: [{label: "Plazas", data: datos.map((fila) => fila.plazas), backgroundColor: "#7b68c7", borderColor: "#55439c", borderWidth: 1, borderRadius: 5, maxBarThickness: 34}]},
        options: {responsive: true, maintainAspectRatio: false, plugins: {legend: {display: false}, tooltip: {callbacks: {label: etiquetaTooltip}}}, scales: {x: {ticks: {autoSkip: false, maxRotation: 45, minRotation: 0}}, y: {beginAtZero: true, ticks: {precision: 0}}}},
    });
}

function crearGraficoPuestosAnual(datos) {
    const colores = ["#2457d6", "#e17c35", "#3d9b6d", "#a34fa8", "#d24d62"];
    reemplazarGrafico("puestos-anual", "grafico-puestos-anual", {
        type: "line",
        data: {labels: (datos.years || []).map(String), datasets: (datos.series || []).map((serie, indice) => ({label: serie.label, data: serie.values, borderColor: colores[indice % colores.length], backgroundColor: colores[indice % colores.length], tension: 0.2, fill: false}))},
        options: {responsive: true, maintainAspectRatio: false, interaction: {mode: "index", intersect: false}, plugins: {legend: {display: true, position: "bottom"}, tooltip: {callbacks: {title: tituloTooltipAnual, label: (contexto) => `${contexto.dataset.label}: ${formatoNumero.format(contexto.parsed.y)} plazas`}}}, scales: {x: {ticks: {precision: 0}}, y: {beginAtZero: true, ticks: {precision: 0}}}},
    });
}

function crearGraficoComunidades(datos) {
    reemplazarGrafico("comunidades", "grafico-comunidades", {
        type: "pie",
        data: {labels: datos.map((fila) => fila.comunidad), datasets: [{label: "Plazas", data: datos.map((fila) => fila.plazas), backgroundColor: coloresComunidades.slice(0, datos.length), borderColor: "#fff", borderWidth: 2}]},
        options: {responsive: true, maintainAspectRatio: false, plugins: {legend: {position: "bottom"}, tooltip: {callbacks: {label: etiquetaTooltipConPorcentaje}}}},
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
    const valor = contexto.dataset.data[contexto.dataIndex];
    return `Plazas: ${formatoNumero.format(valor)}`;
}

function tituloTooltipAnual(contextos) {
    return `Año: ${contextos[0].label}`;
}

function etiquetaTooltipConPorcentaje(contexto) {
    const valor = Number(contexto.dataset.data[contexto.dataIndex]);
    const total = contexto.dataset.data.reduce((acumulado, plaza) => acumulado + Number(plaza), 0);
    const porcentaje = total ? valor / total * 100 : 0;
    return `Plazas: ${formatoNumero.format(valor)} (${porcentaje.toLocaleString("es-ES", {maximumFractionDigits: 1})} %)`;
}
