function toggleTheme() {
  const theme = document.getElementById("theme");
  theme.href = theme.href.includes("dark")
    ? "/static/bootstrap.css"
    : "/static/bootstrap-dark.css";
}

// Atualização do QR na Home
if (document.getElementById("qrcode")) {
    function refreshQRHome() {
        fetch("/api/token")
        .then(r => r.json())
        .then(data =>
        {
            document.getElementById("qrcode").innerHTML = "";
            new QRCode(document.getElementById("qrcode"),
                window.location.origin + "/presenca?token=" + data.token
            );
        });
    }
    setInterval(refreshQRHome, 60000);
}

// Busca admin
document.getElementById('busca')?.addEventListener('input', function () {
  const filtro = this.value.toLowerCase();
  document.querySelectorAll("#tabela tbody tr").forEach(tr => {
      tr.style.display = tr.textContent.toLowerCase().includes(filtro) ? "" : "none";
  });
});
