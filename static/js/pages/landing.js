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
        subject: "Application: Front-end Developer role at ApexForge Systems",
        p1: "I came across ApexForge Systems while looking for software companies in Bengaluru that build web and mobile apps, and I would love to join your team.",
        p2: "I build fast, responsive web applications using React, TypeScript, and Tailwind CSS, which matches the stack your team works with.",
        p3: "I am looking for a full-time front-end developer role and have attached my resume. Are you hiring developers right now?",
      },
      executive: {
        subject: "Front-end developer applying to ApexForge Systems",
        p1: "ApexForge Systems has a strong reputation for well-built web and cloud products.",
        p2: "In my last role I built reusable front-end components that cut release time for my team and kept the codebase organized and bug-free.",
        p3: "If you have an opening for a front-end developer, I would welcome a short conversation. My resume is attached.",
      },
      peer: {
        subject: "Application: Front-end Developer, Bengaluru",
        p1: "Hi ApexForge team, I would love to join you as a front-end developer.",
        p2: "I'm a front-end developer working with React and TypeScript, and I love building clean, responsive interfaces. I'd love to be considered for any open developer roles on your team.",
        p3: "My resume is attached. Are you hiring front-end developers right now?",
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
        subject: "Application: Backend Engineer role at VortexLogic Labs",
        p1: "I came across VortexLogic Labs while looking for software companies in Pune, and I would like to apply for a backend engineering role.",
        p2: "I specialize in backend engineering using Python, FastAPI, and Node.js with PostgreSQL. I build fast, reliable APIs and clean database architectures that handle heavy traffic smoothly.",
        p3: "My resume is attached. Do you have any openings for backend engineers?",
      },
      executive: {
        subject: "Backend engineer applying to VortexLogic Labs",
        p1: "VortexLogic Labs' 5.0 rating across 140+ reviews says a lot about how your team works.",
        p2: "I build clean API architectures and automated tests that catch issues before release, and I would like to bring that to your engineering team.",
        p3: "If you are hiring backend engineers, I would welcome a short conversation. My resume is attached.",
      },
      peer: {
        subject: "Application: Full-stack Engineer, Pune",
        p1: "Hi VortexLogic team, I am applying for a full-stack engineering role on your team.",
        p2: "I'm a full-stack engineer passionate about clean code, reliable databases, and intuitive user experiences. I would like to be considered for any open roles.",
        p3: "My resume is attached, and I am happy to share my code projects too.",
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
        subject: "Application: Full-stack AI Developer role at NovaCrest AI",
        p1: "I came across NovaCrest AI while looking for AI product companies in Hyderabad, and I would like to apply to join your team.",
        p2: "I work with Next.js, Python, and modern AI integrations. In my recent builds, I focused on building fast web interfaces that stream AI responses smoothly without delays.",
        p3: "My resume is attached. Are you hiring full-stack or AI developers?",
      },
      executive: {
        subject: "Full-stack engineer applying to NovaCrest AI",
        p1: "NovaCrest AI's focus on practical, AI-powered software products is exactly where modern technology is heading.",
        p2: "I have turned AI prototypes into polished, reliable web applications, and I would like to do the same as part of your product team.",
        p3: "If NovaCrest AI is hiring full-stack engineers, I would welcome a chance to share my work. My resume is attached.",
      },
      peer: {
        subject: "Application: Developer, Hyderabad",
        p1: "Hi NovaCrest team, I am a developer applying to join your product team.",
        p2: "I'm a developer working with Next.js and Python, and I would like to be considered for any open developer roles.",
        p3: "My resume is attached. Are you hiring developers right now?",
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
      <strong class="text-primary">Rahul Vora</strong> / <span class="text-secondary">Resume attached</span>
    </p>
  `;

  // Update tone badge
  const toneLabels = {
    architecture: "Skills & Experience",
    executive: "Results",
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
      label.textContent = "Copy Email";
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
