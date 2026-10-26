(() => {
  const skins = [
    {key:'boreal', name:'Cortina Boreal', detail:'Véus turquesa · filamentos violetas', motion:'Três cortinas translúcidas deslizam em ritmos distintos; pequenos pontos de luz percorrem o horizonte polar.', color:'#7b92ed'},
    {key:'emerald', name:'Gelo Fraturado', detail:'Placas esmeralda · veios ramificados', motion:'Placas de gelo se encontram em fendas finas, com um brilho que atravessa a fratura sem apagar a textura.', color:'#32b99a'},
    {key:'crimson', name:'Tempestade Âmbar', detail:'Bandas jovianas · olho ciclônico', motion:'Faixas de nuvens cruzam a esfera em velocidades diferentes enquanto o olho da tempestade gira lentamente.', color:'#d48b54'},
    {key:'amethyst', name:'Órbita Índigo', detail:'Anel duplo inclinado · lua em trânsito', motion:'Duas linhas orbitais acompanham a curvatura do vidro; um satélite completa o percurso em ciclo contínuo.', color:'#8797da'},
    {key:'solaris', name:'Eclipse Rosé', detail:'Corona luminosa · sombra móvel', motion:'A sombra avança sobre o disco rosado e revela uma borda quente de luz, com um arco fino de refração.', color:'#d77f98'},
    {key:'ocean', name:'Falha Prismática', detail:'Placas ciano · fratura ramificada', motion:'Uma falha principal se divide em veios menores e separa planos de gelo com reflexos azulados.', color:'#43b8bd'},
    {key:'titan', name:'Névoa Violeta', detail:'Véus lilás · profundidade escura', motion:'Camadas de névoa violeta deslizam em profundidades diferentes; a luz difusa aparece e desaparece sob o vidro.', color:'#8a70ae'},
    {key:'io', name:'Crosta Incandescente', detail:'Basalto escuro · rios de magma', motion:'Trincas quentes pulsam sob uma crosta escura e três focos vulcânicos acendem em sequência.', color:'#e76843'},
    {key:'triton', name:'Calota Glacial', detail:'Gelo azul profundo · pluma polar', motion:'Uma calota clara contrasta com o azul profundo; uma pluma sobe entre estrias gravadas no gelo.', color:'#4b8cc5'},
  ];
  let current = 0;
  const orb = document.querySelector('#skinOrb');
  const heroOrb = document.querySelector('#heroOrb');
  const sideLeft = document.querySelector('#sideLeft');
  const sideRight = document.querySelector('#sideRight');
  const rail = document.querySelector('#skinRail');

  function setOrbImage(image, key, direction, animate) {
    if (!image) return;
    const fallback = 'media/skins/' + key + '.png';
    const animated = 'media/skins/' + key + '.webp';
    if (!animate) {
      image.src = animated;
      image.onerror = () => { image.onerror = null; image.src = fallback; };
      return;
    }
    image.classList.remove('orb-enter-left','orb-enter-right','orb-leaving-left','orb-leaving-right');
    image.classList.add(direction >= 0 ? 'orb-leaving-left' : 'orb-leaving-right');
    window.setTimeout(() => {
      image.onerror = () => { image.onerror = null; image.src = fallback; };
      image.src = animated;
      image.classList.remove('orb-leaving-left','orb-leaving-right');
      image.classList.add(direction >= 0 ? 'orb-enter-right' : 'orb-enter-left');
      requestAnimationFrame(() => requestAnimationFrame(() => {
        image.classList.remove('orb-enter-left','orb-enter-right');
      }));
    }, 150);
  }

  function updateSkin(index, direction, animate = true) {
    current = (index + skins.length) % skins.length;
    const skin = skins[current];
    setOrbImage(orb, skin.key, direction, animate);
    setOrbImage(heroOrb, skin.key, direction, animate);
    document.querySelector('#skinName').textContent = skin.name;
    document.querySelector('#skinDesc').textContent = skin.detail;
    document.querySelector('#skinMotion').textContent = skin.motion;
    document.querySelector('#skinCount').textContent = String(current + 1).padStart(2,'0') + ' — 09';
    document.querySelector('.stage-glow').style.background = 'radial-gradient(circle,' + skin.color + '42,transparent 68%)';
    const previous = skins[(current + skins.length - 1) % skins.length];
    const next = skins[(current + 1) % skins.length];
    setOrbImage(sideLeft, previous.key, -direction, animate);
    setOrbImage(sideRight, next.key, direction, animate);
    sideLeft.alt = 'Aparência anterior: ' + previous.name;
    sideRight.alt = 'Próxima aparência: ' + next.name;
    [...rail.children].forEach((button, i) => {
      button.classList.toggle('active', i === current);
      button.setAttribute('aria-selected', i === current ? 'true' : 'false');
    });
  }

  skins.forEach((skin, i) => {
    const button = document.createElement('button');
    button.className = 'skin-pill'; button.type = 'button'; button.role = 'tab';
    button.style.setProperty('--swatch', skin.color); button.textContent = skin.name;
    button.addEventListener('click', () => updateSkin(i, i >= current ? 1 : -1));
    rail.append(button);
  });
  document.querySelector('.carousel-arrow.prev').addEventListener('click', () => updateSkin(current - 1, -1));
  document.querySelector('.carousel-arrow.next').addEventListener('click', () => updateSkin(current + 1, 1));
  document.querySelector('.skin-stage').addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft') updateSkin(current - 1, -1);
    if (event.key === 'ArrowRight') updateSkin(current + 1, 1);
  });
  updateSkin(0, 1, false);

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
    window.setTimeout(() => { image.src = src; image.alt = alt; image.style.opacity = '1'; }, 140);
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

  if ('IntersectionObserver' in window) {
    const reveal = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.classList.add('visible'); reveal.unobserve(entry.target); }
    }), {threshold: .12});
    document.querySelectorAll('.reveal').forEach((element) => reveal.observe(element));
    const navLinks = [...document.querySelectorAll('.nav-link')];
    const sections = navLinks.map((link) => document.querySelector(link.getAttribute('href'))).filter(Boolean);
    const navObserver = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) navLinks.forEach((link) => link.classList.toggle('active', link.hash === '#' + entry.target.id));
    }), {rootMargin:'-35% 0px -55% 0px'});
    sections.forEach((section) => navObserver.observe(section));
  } else {
    document.querySelectorAll('.reveal').forEach((element) => element.classList.add('visible'));
  }
  // Keep the page readable if any later script fails to initialize. Reveal
  // animations are progressive enhancement, so enable hidden states last.
  document.documentElement.classList.add('js-reveal');
})();
