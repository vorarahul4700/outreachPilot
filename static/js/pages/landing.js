/* Homepage example-company demo. Moved unchanged from the inline script in
   templates/landing.html (redesign/v2). The theme toggle now lives in
   static/js/site/theme.js. Active states are styled through the .active class. */

// Specimen Database (Curated realistic mock specimens)
const specimens = [
  {
    id: "af",
    name: "ApexForge Systems",
    monogram: "AF",
    domain: "apexforge.io",
    email: "contact@apexforge.io",
    location: "Bengaluru, Karnataka, IN",
    rating: "4.9 (184 reviews)",
    tech: ["React.js", "TypeScript", "Tailwind CSS", "Next.js"],
    pitches: {
      architecture: {
        subject: "Frontend development & web app architecture at ApexForge Systems",
        p1: "I came across ApexForge Systems while researching top software development agencies specializing in custom web and mobile apps. Your 4.9 rating across 184 client reviews really caught my attention.",
        p2: "I build fast, responsive web applications using React, TypeScript, and Tailwind CSS. I noticed you build custom client solutions where smooth user experience and fast loading times are essential.",
        p3: "I'm currently looking for new projects and full-time opportunities with great development teams. Are you taking on new developers right now?",
      },
      executive: {
        subject: "Helping ApexForge Systems deliver client web projects faster",
        p1: "ApexForge Systems has a stellar reputation for delivering end-to-end cloud and web products for clients.",
        p2: "I help agencies speed up client delivery by building clean, reusable front-end design systems and keeping codebases organized and bug-free.",
        p3: "If your team is looking for a dependable front-end developer to help with upcoming client projects, I'd welcome a brief 5-minute conversation.",
      },
      peer: {
        subject: "Quick hello from a front-end developer in Bengaluru",
        p1: "Hey ApexForge team: I really admire the quality of web platforms your team has shipped over recent years.",
        p2: "I'm a front-end developer working with React and TypeScript, and I love building clean, responsive interfaces. I'd love to connect with your team for upcoming project opportunities.",
        p3: "Would you have 5 minutes this week for a quick chat?",
      }
    }
  },
  {
    id: "vl",
    name: "VortexLogic Labs",
    monogram: "VL",
    domain: "vortexlogic.dev",
    email: "contact@vortexlogic.dev",
    location: "Pune, Maharashtra, IN",
    rating: "5.0 (142 reviews)",
    tech: ["Node.js", "Python", "FastAPI", "PostgreSQL"],
    pitches: {
      architecture: {
        subject: "Backend API development & Python engineering at VortexLogic Labs",
        p1: "I've been following VortexLogic Labs' work building custom software and scalable backend platforms in Pune.",
        p2: "I specialize in backend engineering using Python, FastAPI, and Node.js with PostgreSQL. I build fast, reliable APIs and clean database architectures that handle heavy traffic smoothly.",
        p3: "I'm looking for new software engineering roles where I can help build rock-solid systems. Do you have any openings on your core development team?",
      },
      executive: {
        subject: "Reliable senior backend engineering capacity for VortexLogic Labs",
        p1: "VortexLogic Labs' consistent 5.0 delivery track record across 140+ client engagements demonstrates top-tier execution.",
        p2: "I help software firms ship client deliverables on time by building clean API architectures and automated tests that catch issues before release.",
        p3: "If you're looking for extra engineering support on upcoming client deliverables, I'd welcome a quick 5-minute introductory chat.",
      },
      peer: {
        subject: "Connecting with the VortexLogic engineering team",
        p1: "Hi VortexLogic team: love the solid software foundation you've established across Python and Node.js backend systems.",
        p2: "I'm a full-stack engineer passionate about clean code, reliable databases, and intuitive user experiences. Would love to introduce myself for upcoming opportunities.",
        p3: "Happy to share my recent code projects and portfolio if you have 5 minutes.",
      }
    }
  },
  {
    id: "nc",
    name: "NovaCrest AI",
    monogram: "NC",
    domain: "novacrest.ai",
    email: "contact@novacrest.ai",
    location: "Hyderabad, Telangana, IN",
    rating: "4.9 (96 reviews)",
    tech: ["Next.js", "PyTorch", "AWS", "PostgreSQL"],
    pitches: {
      architecture: {
        subject: "Next.js & AI application development at NovaCrest AI",
        p1: "I noticed NovaCrest AI is actively building smart SaaS products and modern cloud solutions in Hyderabad. Your portfolio looks fantastic.",
        p2: "I work with Next.js, Python, and modern AI integrations. In my recent builds, I focused on building fast web interfaces that stream AI responses smoothly without delays.",
        p3: "I'm eager to bring hands-on full-stack and AI development skills to NovaCrest AI. Would your technical team be open to a 10-minute introductory call?",
      },
      executive: {
        subject: "Full-stack product engineering support for NovaCrest AI",
        p1: "NovaCrest AI's focus on practical, AI-powered software products is exactly where modern technology is heading.",
        p2: "I help SaaS companies turn AI prototypes into polished, reliable web applications that customers love using.",
        p3: "If NovaCrest AI is looking for extra developer firepower to build new product features this quarter, I'd welcome a chance to share my work.",
      },
      peer: {
        subject: "Fellow developer saying hello to the NovaCrest AI team",
        p1: "Hey NovaCrest team: big fan of the AI-driven software products you've been launching.",
        p2: "I'm a developer working with Next.js and Python, and I'm exploring new teams to build with. Would love to connect with fellow builders at NovaCrest.",
        p3: "Are you open to an informal conversation about what you're working on?",
      }
    }
  }
];

let currentSpecimenIdx = 0;
let currentTone = "architecture";

function updateSpecimenUI() {
  const sp = specimens[currentSpecimenIdx];
  const pitchData = sp.pitches[currentTone];

  // Specimen metadata
  document.getElementById("specimen-mono").textContent = sp.monogram;
  document.getElementById("specimen-name").textContent = sp.name;
  document.getElementById("specimen-domain").textContent = sp.domain;
  document.getElementById("specimen-email").textContent = sp.email;
  document.getElementById("specimen-location").textContent = sp.location;
  document.getElementById("specimen-rating").textContent = sp.rating;

  // Tech pills
  const techContainer = document.getElementById("specimen-tech-pills");
  techContainer.innerHTML = sp.tech.map(t => `<span class="px-2 py-0.5 rounded text-[11px] font-mono bg-surface-container text-on-surface-variant border border-outline">${t}</span>`).join("");

  // Pitch terminal
  document.getElementById("pitch-to").textContent = sp.email;
  document.getElementById("pitch-subject").textContent = pitchData.subject;
  
  const bodyContainer = document.getElementById("pitch-body");
  bodyContainer.innerHTML = `
    <p>Hi ${escapeHTML(sp.name.split(' ')[0])} Team,</p>
    <p>${escapeHTML(pitchData.p1)}</p>
    <p>${escapeHTML(pitchData.p2)}</p>
    <p>${escapeHTML(pitchData.p3)}</p>
    <p class="text-on-surface-variant text-xs pt-1 font-mono">
      Best regards,<br/>
      <strong class="text-primary">Rahul Vora</strong> / <span class="text-secondary">Portfolio &amp; GitHub Profile Attached</span>
    </p>
  `;

  // Update tone badge
  const toneLabels = {
    architecture: "Skills & Experience",
    executive: "Business & Results",
    peer: "Casual & Friendly"
  };
  document.getElementById("tone-badge").textContent = toneLabels[currentTone];
}

function selectSpecimen(idx) {
  currentSpecimenIdx = idx;
  const tabs = document.querySelectorAll(".specimen-tab");
  tabs.forEach((tab, i) => {
    if (i === idx) {
      tab.classList.add("active", "border-primary", "bg-surface-container");
      tab.classList.remove("border-outline", "bg-surface-container-lowest");
      const title = tab.querySelector(".font-display");
      if (title) title.classList.replace("text-on-surface-variant", "text-primary");
    } else {
      tab.classList.remove("active", "border-primary", "bg-surface-container");
      tab.classList.add("border-outline", "bg-surface-container-lowest");
      const title = tab.querySelector(".font-display");
      if (title) title.classList.replace("text-primary", "text-on-surface-variant");
    }
  });
  updateSpecimenUI();
}

function setPitchTone(tone) {
  currentTone = tone;
  const buttons = document.querySelectorAll(".tone-btn");
  buttons.forEach(btn => {
    const isMatch = btn.getAttribute("onclick").includes(`'${tone}'`);
    if (isMatch) {
      btn.classList.add("active", "border-primary", "bg-surface-container", "text-primary");
      btn.classList.remove("border-outline", "bg-surface-container-lowest", "text-on-surface-variant");
    } else {
      btn.classList.remove("active", "border-primary", "bg-surface-container", "text-primary");
      btn.classList.add("border-outline", "bg-surface-container-lowest", "text-on-surface-variant");
    }
  });
  updateSpecimenUI();
}

function copyPitch() {
  const sp = specimens[currentSpecimenIdx];
  const pitch = sp.pitches[currentTone];
  const text = `To: ${sp.email}\nSubject: ${pitch.subject}\n\nHi ${sp.name.split(' ')[0]} Team,\n\n${pitch.p1}\n\n${pitch.p2}\n\n${pitch.p3}\n\nBest regards,\nRahul Vora`;
  
  navigator.clipboard.writeText(text).then(() => {
    const icon = document.getElementById("copy-icon");
    const label = document.getElementById("copy-text");
    icon.textContent = "done";
    label.textContent = "Copied!";
    setTimeout(() => {
      icon.textContent = "content_copy";
      label.textContent = "Copy Pitch";
    }, 2000);
  });
}

function escapeHTML(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Smooth-scroll anchor navigation
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function (e) {
    const targetId = this.getAttribute('href');
    if (targetId && targetId !== '#') {
      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        e.preventDefault();
        targetEl.scrollIntoView({ behavior: 'smooth' });
        history.pushState(null, '', targetId);
      }
    }
  });
});

// Initialize UI on load
document.addEventListener("DOMContentLoaded", () => {
  updateSpecimenUI();
});
