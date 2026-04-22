export function isDualTeamAdmin(member = {}) {
  const character = Number(member?.character);
  const isNavLead = Boolean(member?.isNavLead);
  const isServoLead = Boolean(member?.isServoLead);
  return character === 0 && isNavLead && isServoLead;
}

export function shouldHideMemberInSelector(member = {}) {
  return isDualTeamAdmin(member);
}

