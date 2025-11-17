document.addEventListener('DOMContentLoaded', function(){
  const btn = document.getElementById('themeToggle');
  const init = () => {
    const t = localStorage.getItem('site-theme') || 'light';
    document.body.setAttribute('data-theme', t);
    if(btn){
      btn.setAttribute('aria-pressed', t === 'dark');
      btn.innerText = t === 'dark' ? 'Escuro' : 'Claro';
    }
  };
  init();
  btn && btn.addEventListener('click', function(){
    const cur = document.body.getAttribute('data-theme') || 'light';
    const nxt = cur === 'light' ? 'dark' : 'light';
    document.body.setAttribute('data-theme', nxt);
    localStorage.setItem('site-theme', nxt);
    btn.setAttribute('aria-pressed', nxt === 'dark');
    btn.innerText = nxt === 'dark' ? 'Escuro' : 'Claro';
  });
});
