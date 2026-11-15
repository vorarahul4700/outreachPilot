/* OutreachPilot app: Candidate profile tab: loading and showing the parsed resume.
   Moved unchanged out of static/js/app.js (redesign Phase 6). These functions
   use no shared state, so they run the same as globals. Load before app.js. */

async function loadCandidateProfile() {
  try {
    const res = await fetch("/api/resume/profile");
    if (res.status === 401) return;
    const data = await res.json();
    if (data.resume_link) {
      const linkEl = document.getElementById("input-resume-link");
      if (linkEl) linkEl.value = data.resume_link;
    }
    if (data.target_role) {
      const roleEl = document.getElementById("input-target-role");
      if (roleEl) roleEl.value = data.target_role;
    }
    if (data.profile) {
      renderCandidateProfile(data.profile);
    }
  } catch (err) {
    console.warn("Could not load candidate profile:", err);
  }
}

function renderCandidateProfile(profile) {
  if (!profile) return;
  const pitchEl = document.getElementById("profile-pitch");
  if (pitchEl && profile.elevator_pitch) {
    pitchEl.textContent = profile.elevator_pitch;
  }

  const archetypeBadge = document.getElementById("profile-archetype-badge");
  if (archetypeBadge) {
    if (profile.archetype) {
      archetypeBadge.textContent = profile.archetype;
      archetypeBadge.classList.remove("hidden");
    } else {
      archetypeBadge.classList.add("hidden");
    }
  }

  const skillsContainer = document.getElementById("profile-skills");
  if (skillsContainer && profile.top_skills) {
    skillsContainer.innerHTML = profile.top_skills.map(s => `
      <span class="skill-chip">${escapeHTML(s)}</span>
    `).join("");
  }

  const achContainer = document.getElementById("profile-achievements");
  if (achContainer) {
    const achievements = profile.strong_points || profile.key_achievements;
    if (achievements && achievements.length > 0) {
      achContainer.innerHTML = achievements.map(a => `
        <li>${escapeHTML(a)}</li>
      `).join("");
    }
  }

  const rolesSec = document.getElementById("profile-roles-section");
  const rolesContainer = document.getElementById("profile-best-fit-roles");
  if (rolesSec && rolesContainer) {
    if (profile.best_fit_roles && profile.best_fit_roles.length > 0) {
      rolesContainer.innerHTML = profile.best_fit_roles.map(r => `
        <span class="role-chip">${escapeHTML(r)}</span>
      `).join("");
      rolesSec.classList.remove("hidden");
    } else {
      rolesSec.classList.add("hidden");
    }
  }

  const atsSec = document.getElementById("profile-ats-section");
  const atsContainer = document.getElementById("profile-ats-keywords");
  if (atsSec && atsContainer) {
    if (profile.ats_keywords && profile.ats_keywords.length > 0) {
      atsContainer.innerHTML = profile.ats_keywords.map(k => `
        <span class="kw-chip">${escapeHTML(k)}</span>
      `).join("");
      atsSec.classList.remove("hidden");
    } else {
      atsSec.classList.add("hidden");
    }
  }

  const detailedAnalysisEl = document.getElementById("profile-detailed-analysis");
  if (detailedAnalysisEl && profile.detailed_profile_analysis) {
    detailedAnalysisEl.dataset.rawText = profile.detailed_profile_analysis;
    detailedAnalysisEl.innerHTML = formatMarkdown(profile.detailed_profile_analysis);
  }
}
