function toggleTheme() {
    const theme = document.getElementById("theme");
    theme.href = theme.href.includes("dark") ?
        "/static/bootstrap.css" : "/static/bootstrap-dark.css";
}

document.getElementById('busca')?.addEventListener('input', function () {
    const filtro = this.value.toLowerCase();
    document.querySelectorAll("#tabela tbody tr").forEach(tr => {
        tr.style.display = tr.textContent.toLowerCase().includes(filtro) ? "" : "none";
    });
});

fetch("/api/graficos")
.then(r => r.json())
.then(data => {
    new Chart(document.getElementById("grafSetor"), {
        type: "pie",
        data: { labels: Object.keys(data.setores), datasets: [{ data: Object.values(data.setores) }] }
    });
});
