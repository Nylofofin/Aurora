(() => {
  const skins = [
    ['boreal','Véu Boreal','Azul polar · cortina de aurora','Cortinas azul-turquesa deslizam sobre vidro polar enquanto a luz percorre a superfície.','#6961c7'],
    ['emerald','Europa','Verde glacial · placas de gelo','Veios finos encontram-se no centro como placas de gelo sob tensão; o brilho respira devagar.','#247d70'],
    ['crimson','Júpiter','Âmbar · faixas atmosféricas','Nuvens douradas cruzam a esfera em bandas; um olho de tempestade se move entre elas.','#dfa45f'],
    ['amethyst','Reia','Índigo mineral · anel duplo','Dois anéis estreitos inclinam-se pelo vidro, com uma pequena lua percorrendo o mesmo plano.','#9caee7'],
    ['solaris','Dione','Rosa de eclipse · corona móvel','Uma sombra escura avança sobre a esfera rosada; a corona clara pulsa ao redor do eclipse.','#d77f98'],
    ['ocean','Miranda','Ciano abissal · falha cristalina','Uma fratura angular atravessa o azul-ciano e revela planos de gelo com brilho próprio.','#58cfc6'],
    ['titan','Titã','Índigo nebuloso · halo atmosférico','Um halo largo e quase horizontal contorna o índigo; seu satélite completa uma órbita lenta.','#777eae'],
    ['io','Ío','Ouro vulcânico · fratura incandescente','Uma fissura pulsa do dourado ao vermelho, como lava acesa sob uma camada de vidro.','#f18c39'],
    ['triton','Tritão','Azul polar · correntes oceânicas','Três correntes curvas atravessam um mar glacial em ritmos sobrepostos.','#80d2e8'],
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
    orb.src = `media/skins/${key}.png`;
    orb.alt = `Prévia oficial da aparência ${name}`;
    if (heroOrb) {
      heroOrb.src = `media/skins/${key}.png`;
      heroOrb.alt = `Bolha oficial da Aurora no estilo ${name}`;
    }
    document.querySelector('#skinName').textContent = name;
    document.querySelector('#skinDesc').textContent = description;
    document.querySelector('#skinMotion').textContent = motion;
    document.querySelector('#skinCount').textContent = `${String(current + 1).padStart(2,'0')} — 09`;
    document.querySelector('.stage-glow').style.background = `radial-gradient(circle,${color}35,transparent 68%)`;
    const previous = skins[(current + skins.length - 1) % skins.length];
    const next = skins[(current + 1) % skins.length];
    sideLeft.src = `media/skins/${previous[0]}.png`;
    sideRight.src = `media/skins/${next[0]}.png`;
    sideLeft.alt = `Aparência anterior: ${previous[1]}`;
    sideRight.alt = `Próxima aparência: ${next[1]}`;
    [...rail.children].forEach((button, i) => {
      button.classList.toggle('active', i === current);
      button.setAttribute('aria-selected', i === current ? 'true' : 'false');
    });
  };
  skins.forEach(([key, name, _description, _motion, color], i) => {
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
