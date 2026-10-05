"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const raiz = document.querySelector(".dias-inhabiles");
    if (!raiz) return;
    const detalle = document.querySelector("#detalle-dia-inhabil");
    let colores = {};
    try { colores = JSON.parse(raiz.dataset.colores || "{}"); } catch (_) { colores = {}; }
    const comunidades = () => [...raiz.querySelectorAll("input[name='comunidad']")];
    document.querySelector("#dias-inhabiles-seleccionar-todas")?.addEventListener("click", () => comunidades().forEach(caja => { caja.checked = true; }));
    document.querySelector("#dias-inhabiles-deseleccionar-todas")?.addEventListener("click", () => comunidades().forEach(caja => { caja.checked = false; }));
    const crear = (etiqueta, texto) => { const nodo = document.createElement(etiqueta); nodo.textContent = texto; return nodo; };
    const mostrarError = texto => detalle.replaceChildren(crear("h2", "Detalle del día"), crear("p", texto));
    const mostrar = dato => {
        const titulo = crear("h2", dato.fecha);
        if (!dato.inhabiles.length) { detalle.replaceChildren(titulo, crear("p", "No hay días inhábiles registrados para la selección actual.")); return; }
        const lista = document.createElement("ul");
        dato.inhabiles.forEach(entrada => {
            const item = document.createElement("li");
            const ambito = entrada.ambito === "NACIONAL" ? "Nacional" : (entrada.comunidad_autonoma || "Autonómico");
            const etiqueta = crear("strong", ambito);
            if (entrada.comunidad_autonoma && colores[entrada.comunidad_autonoma]) {
                etiqueta.className = `dias-inhabiles-community-label ${colores[entrada.comunidad_autonoma].replace("dias-inhabiles-color--", "dias-inhabiles-text--")}`;
            }
            item.append(etiqueta, document.createTextNode(` · ${entrada.categoria || "Día inhábil"}: ${entrada.festividad || "fiesta no identificada en la publicación"}`));
            const fuentes = entrada.fuentes?.length ? entrada.fuentes : (entrada.fuente_url ? [entrada.fuente_url] : []);
            fuentes.forEach((fuente, indice) => { const enlace = document.createElement("a"); enlace.href = fuente; enlace.target = "_blank"; enlace.rel = "noopener noreferrer"; enlace.textContent = fuentes.length > 1 ? `Fuente oficial ${indice + 1}` : "Fuente oficial"; item.append(document.createTextNode(" · "), enlace); });
            lista.append(item);
        });
        const festividades = crear("p", dato.festividades.length ? `Fiestas celebradas: ${dato.festividades.join("; ")}` : "La publicación no identifica una fiesta concreta para este día.");
        detalle.replaceChildren(titulo, lista, festividades);
    };
    raiz.querySelectorAll(".dias-inhabiles-day[data-fecha]").forEach(boton => boton.addEventListener("click", async () => {
        raiz.querySelectorAll(".dias-inhabiles-day[aria-pressed='true']").forEach(anterior => anterior.removeAttribute("aria-pressed"));
        boton.setAttribute("aria-pressed", "true");
        const parametros = new URLSearchParams({fecha: boton.dataset.fecha, comunidades_aplicadas: "1"});
        raiz.querySelectorAll("input[name='comunidad']:checked").forEach(caja => parametros.append("comunidad", caja.value));
        try { const respuesta = await fetch(`/api/dias-inhabiles/dia?${parametros}`); const dato = await respuesta.json(); if (!respuesta.ok) throw new Error(dato.error || "No se pudo obtener el detalle."); mostrar(dato); }
        catch (error) { mostrarError(error.message || "No se pudo obtener el detalle."); }
    }));
});
