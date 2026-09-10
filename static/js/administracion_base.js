(() => {
  const endpoint = "/api/administracion/base-datos", byId = (id) => document.getElementById(id);
  const request = async (path) => { const response = await fetch(`${endpoint}/${path}`, {method: "POST"}); const data = await response.json(); if (!response.ok) throw new Error(data.error || "No se pudo completar la operación."); return data; };
  const message = (id, text) => { const item = byId(id); item.textContent = text; item.hidden = false; };
  const resumenPublicacion = (nodo, manifest) => {
    const filas = [
      ["Estructura", manifest.schema_version],
      ["Datos", manifest.data_version],
      ["Tamaño", `${manifest.size_bytes} bytes`],
      ["SHA-256", manifest.sha256],
      ["Comprobación", "Correcta"],
    ];
    nodo.replaceChildren(...filas.flatMap(([etiqueta, valor]) => {
      const termino = document.createElement("dt"), descripcion = document.createElement("dd");
      termino.textContent = etiqueta; descripcion.textContent = valor;
      return [termino, descripcion];
    }));
  };
  let polling = null;
  const stopPolling = () => { if (polling) { clearInterval(polling); polling = null; } };
  const refreshJob = async () => { try { const response = await fetch(`${endpoint}/publicacion`), job = await response.json(), box = byId("estado-publicacion"), spinner = box.querySelector(".admin-spinner"); if (job.estado === "sin_trabajo") { box.hidden = true; stopPolling(); return; } const terminal = job.terminal || ["completado", "error", "cancelado"].includes(job.estado); box.hidden = false; spinner.hidden = terminal; box.classList.toggle("admin-status--final", terminal); box.querySelector("span:last-child").textContent = job.error || `${job.fase} Tiempo transcurrido: ${job.transcurrido_segundos}s.`; if (terminal) stopPolling(); } catch (_) { stopPolling(); } };
  document.addEventListener("click", async (event) => { const action = event.target.closest("[data-accion]")?.dataset.accion; if (!action) return; try { if (action === "verificar") { const r = await request("verificar"); message("resultado-verificacion", `La base está en buen estado (estructura ${r.schema_version}, datos ${r.data_version}).`); } if (action === "version-publicada") { const r = await request("version-publicada"); if (r.estado === "no_publicada") message("resultado-version", `${r.mensaje} Puede crear la primera copia mediante “Publicar base local”.`); else if (r.estado === "publicacion_incompleta") message("resultado-version", r.mensaje); else message("resultado-version", `${r.mensaje} Publicada: estructura ${r.publicada.schema_version}, datos ${r.publicada.data_version}, ${r.publicada.size_bytes} bytes, ${r.publicada.published_at}.`); } if (action === "preparar-publicacion") { const r = await request("preparar-publicacion"), m = r.manifest; resumenPublicacion(byId("resumen-publicacion"), m); byId("confirmacion-publicacion").hidden = false; } if (action === "cancelar-publicacion") byId("confirmacion-publicacion").hidden = true; if (action === "confirmar-publicacion") { stopPolling(); byId("confirmacion-publicacion").hidden = true; await request("confirmar-publicacion"); await refreshJob(); polling = setInterval(refreshJob, 1000); } } catch (error) { message(action === "version-publicada" ? "resultado-version" : "resultado-verificacion", error.message); } });
  refreshJob();
})();
