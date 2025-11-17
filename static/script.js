// static/script.js
document.addEventListener('DOMContentLoaded', function(){
  // home QR auto refresh
  const qElem = document.getElementById('qrcode');
  if(qElem){
    const renderHomeQR = (token) => {
      qElem.innerHTML = "";
      new QRCode(qElem, {text: window.location.origin + "/presenca?token=" + token, width:260, height:260});
    };
    fetch('/api/token').then(r=>r.json()).then(d => renderHomeQR(d.token));
    setInterval(()=> fetch('/api/token').then(r=>r.json()).then(d => renderHomeQR(d.token)), 60000);
  }

  // simple theme toggle (keeps as before)
  const btn = document.getElementById('themeToggle');
  btn && btn.addEventListener('click', () => {
    const cur = document.body.getAttribute('data-theme') || 'light';
    const nxt = cur === 'light' ? 'dark' : 'light';
    document.body.setAttribute('data-theme', nxt);
    localStorage.setItem('site-theme', nxt);
    btn.innerText = nxt === 'dark' ? 'Escuro' : 'Claro';
  });
});
