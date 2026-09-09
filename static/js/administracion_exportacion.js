(() => {
  const endpoint = "/api/administracion/base-datos/exportacion";
  const boton = document.getElementById("boton-preparar-exportacion-xlsx");
  const enlace = document.getElementById("enlace-descargar-exportacion-xlsx");
  const estado = document.getElementById("estado-exportacion-xlsx");
  if (!boton || !enlace || !estado) return;

  const texto = estado.querySelector("span:last-child");
  const spinner = estado.querySelector(".admin-spinner");
  let polling = null;

  const detenerPolling = () => {
    if (polling) {
      clearInterval(polling);
      polling = null;
    }
  };

  const deshabilitarDescarga = () => {
    enlace.removeAttribute("href");
    enlace.setAttribute("aria-disabled", "true");
    enlace.setAttribute("tabindex", "-1");
  };

  const habilitarDescarga = () => {
    enlace.setAttribute("href", enlace.dataset.url);
    enlace.removeAttribute("aria-disabled");
    enlace.removeAttribute("tabindex");
  };

  const mostrar = (mensaje, {girando = false, exito = false} = {}) => {
    estado.hidden = false;
    texto.textContent = mensaje;
    spinner.hidden = !girando;
    estado.classList.toggle("admin-status--success", exito);
  };

  const aplicarEstado = (trabajo) => {
    const actual = trabajo?.estado || "sin_trabajo";
    if (actual === "sin_trabajo") {
      estado.hidden = true;
      deshabilitarDescarga();
      boton.disabled = false;
      boton.textContent = "Preparar Excel";
      detenerPolling();
      return;
    }
    if (actual === "preparando") {
      deshabilitarDescarga();
      boton.disabled = true;
      boton.textContent = "Preparando Excel...";
      mostrar("Preparando Excel...", {girando: true});
      return;
    }
    if (actual === "completada") {
      boton.disabled = false;
      boton.textContent = "Volver a preparar un Excel";
      habilitarDescarga();
      mostrar("Excel preparado", {exito: true});
      detenerPolling();
      return;
    }
    deshabilitarDescarga();
    boton.disabled = false;
    boton.textContent = "Reintentar";
    mostrar(trabajo?.error || "No se pudo preparar el Excel.");
    detenerPolling();
  };

  const consultar = async () => {
    try {
      const respuesta = await fetch(endpoint);
      const trabajo = await respuesta.json();
      if (!respuesta.ok) throw new Error();
      aplicarEstado(trabajo);
    } catch (_) {
      boton.disabled = false;
      mostrar("No se pudo consultar el estado de la exportación.");
      detenerPolling();
    }
  };

  const iniciarPolling = () => {
    if (!polling) polling = setInterval(consultar, 2000);
  };

  boton.addEventListener("click", async () => {
    if (boton.disabled) return;
    boton.disabled = true;
    deshabilitarDescarga();
    mostrar("Preparando Excel...", {girando: true});
    try {
      const respuesta = await fetch(endpoint, {method: "POST"});
      const datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error || "No se pudo iniciar la exportación.");
      aplicarEstado(datos.trabajo);
      if (datos.trabajo.estado === "preparando") iniciarPolling();
    } catch (_) {
      boton.disabled = false;
      mostrar("No se pudo iniciar la exportación. Puedes intentarlo de nuevo.");
    }
  });

  enlace.addEventListener("click", (evento) => {
    if (enlace.getAttribute("aria-disabled") === "true") evento.preventDefault();
  });

  consultar();
})();
