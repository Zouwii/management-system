export function isDualTeamAdmin(member = {}) {
  const character = Number(member?.character);
  // character=9 内置管理员
  if (character === 9) return true;
  const isNavLead = Boolean(member?.isNavLead);
  const isServoLead = Boolean(member?.isServoLead);
  return character === 0 && isNavLead && isServoLead;
}

export function shouldHideMemberInSelector(member = {}) {
  return isDualTeamAdmin(member);
}

