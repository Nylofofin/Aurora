(() => {
  const skins = [
    ['boreal','Véu Boreal','Azul-violeta · vidro refratado','#4d9cff'],
    ['emerald','Europa','Verde mineral · porcelana','#56d6ae'],
    ['crimson','Júpiter','Âmbar · faixas atmosféricas','#e5a45e'],
    ['amethyst','Reia','Lavanda · anel inclinado','#9b9fe2'],
    ['solaris','Dione','Rosa-violeta · eclipse','#c17da9'],
    ['ocean','Miranda','Ciano · crista de gelo','#52c4d1'],
    ['titan','Titã','Índigo · halo enevoado','#7f89c1'],
    ['io','Ío','Mel vulcânico · fissura','#ed8743'],
    ['triton','Tritão','Azul glacial · correntes polares','#59c3df'],
  ];
  let current = 0;
  const orb = document.querySelector('#skinOrb');
  const heroOrb = document.querySelector('#heroOrb');
  const sideLeft = document.querySelector('#sideLeft');
  const sideRight = document.querySelector('#sideRight');
  const rail = document.querySelector('#skinRail');
  const updateSkin = (index) => {
    current = (index + skins.length) % skins.length;
    const [key, name, description, color] = skins[current];
    orb.className = `skin-orb skin-${key}`;
    if (heroOrb) heroOrb.className = `hero-orb skin-${key}`;
    document.querySelector('#skinName').textContent = name;
    document.querySelector('#skinDesc').textContent = description;
    document.querySelector('#skinCount').textContent = `${String(current + 1).padStart(2,'0')} — 09`;
    document.querySelector('.stage-glow').style.background = `radial-gradient(circle,${color}35,transparent 68%)`;
    sideLeft.className = `side-orb side-left skin-${skins[(current + skins.length - 1) % skins.length][0]}`;
    sideRight.className = `side-orb side-right skin-${skins[(current + 1) % skins.length][0]}`;
    [...rail.children].forEach((button, i) => {
      button.classList.toggle('active', i === current);
      button.setAttribute('aria-selected', i === current ? 'true' : 'false');
    });
  };
  skins.forEach(([key, name, _description, color], i) => {
    const button = document.createElement('button');
    button.className = 'skin-pill'; button.type = 'button'; button.role = 'tab';
    button.style.setProperty('--swatch', color); button.textContent = name;
    button.addEventListener('click', () => updateSkin(i)); rail.append(button);
  });
  document.querySelector('.carousel-arrow.prev').addEventListener('click', () => updateSkin(current - 1));
  document.querySelector('.carousel-arrow.next').addEventListener('click', () => updateSkin(current + 1));
  document.querySelector('.skin-stage').addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft') updateSkin(current - 1);
    if (event.key === 'ArrowRight') updateSkin(current + 1);
  });
  updateSkin(0);

  const demos = {
    skins: ['Aparências','CARROSSEL DE APARÊNCIAS','media/onboarding-skins.gif','Demonstração animada das aparências da Aurora'],
    transitions: ['Onboarding','TRANSIÇÕES DO ONBOARDING','media/onboarding-transitions.gif','Demonstração das transições das páginas do onboarding'],
    voices: ['Vozes','ESCOLHA DE VOZ','media/onboarding-voices.gif','Demonstração da escolha de voz no onboarding'],
    sounds: ['Sons','ASSINATURAS SONORAS','media/onboarding-sounds.gif','Demonstração das opções de sons da Aurora'],
  };
  document.querySelectorAll('.demo-tab').forEach((tab) => tab.addEventListener('click', () => {
    document.querySelectorAll('.demo-tab').forEach((item) => { item.classList.toggle('active', item === tab); item.setAttribute('aria-selected', item === tab ? 'true' : 'false'); });
    const [title, label, src, alt] = demos[tab.dataset.demo];
    const image = document.querySelector('#demoImage');
    image.style.opacity = '0';
    window.setTimeout(() => { image.src = src; image.alt = alt; image.onload = () => { image.style.opacity = '1'; }; }, 140);
    document.querySelector('#demoTitle').textContent = label;
  }));

  const menuButton = document.querySelector('.menu-toggle');
  menuButton.addEventListener('click', () => {
    const open = menuButton.getAttribute('aria-expanded') !== 'true';
    menuButton.setAttribute('aria-expanded', String(open));
    document.querySelector('.main-nav').classList.toggle('open', open);
  });
  document.querySelectorAll('.main-nav a').forEach((link) => link.addEventListener('click', () => {
    document.querySelector('.main-nav').classList.remove('open'); menuButton.setAttribute('aria-expanded','false');
  }));
  const reveal = new IntersectionObserver((entries) => entries.forEach((entry) => {
    if (entry.isIntersecting) { entry.target.classList.add('visible'); reveal.unobserve(entry.target); }
  }), {threshold: .12});
  document.querySelectorAll('.reveal').forEach((element) => reveal.observe(element));
  const navLinks = [...document.querySelectorAll('.nav-link')];
  const sections = navLinks.map((link) => document.querySelector(link.getAttribute('href'))).filter(Boolean);
  const navObserver = new IntersectionObserver((entries) => entries.forEach((entry) => {
    if (entry.isIntersecting) navLinks.forEach((link) => link.classList.toggle('active', link.hash === `#${entry.target.id}`));
  }), {rootMargin:'-35% 0px -55% 0px'});
  sections.forEach((section) => navObserver.observe(section));
})();
