"use strict";

const botonMenu = document.querySelector(".site-menu-button");
const navegacion = document.querySelector("#site-navigation");

if (botonMenu && navegacion) {
    const escritorio = window.matchMedia("(min-width: 961px)");
    const establecerMenu = (abierto, devolverFoco = false) => {
        navegacion.classList.toggle("is-open", abierto);
        botonMenu.setAttribute("aria-expanded", String(abierto));
        botonMenu.setAttribute("aria-label", abierto ? "Cerrar menú de navegación" : "Abrir menú de navegación");
        if (devolverFoco) botonMenu.focus();
    };

    botonMenu.addEventListener("click", () => {
        const abierto = botonMenu.getAttribute("aria-expanded") === "true";
        establecerMenu(!abierto);
    });

    navegacion.querySelectorAll("a").forEach(enlace => {
        enlace.addEventListener("click", () => establecerMenu(false));
    });

    document.addEventListener("keydown", evento => {
        if (evento.key === "Escape" && botonMenu.getAttribute("aria-expanded") === "true") {
            establecerMenu(false, true);
        }
    });

    const restablecerEnEscritorio = () => {
        if (escritorio.matches) establecerMenu(false);
    };
    escritorio.addEventListener("change", restablecerEnEscritorio);
    window.addEventListener("resize", restablecerEnEscritorio);
    establecerMenu(false);
    document.documentElement.classList.replace("no-js", "js");
}
