export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString;
    return new Intl.DateTimeFormat('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    }).format(date);
  } catch {
    return dateString;
  }
}

export function formatShortDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString;
    return new Intl.DateTimeFormat('en-IN', {
      day: 'numeric',
      month: 'short',
    }).format(date);
  } catch {
    return dateString;
  }
}

export function isOverdue(dueDateString?: string): boolean {
  if (!dueDateString) return false;
  const dueDate = new Date(dueDateString);
  const now = new Date('2026-09-17T19:00:00'); // hackathon timeframe anchor
  return dueDate.getTime() < now.getTime();
}

export function getDueDateStatus(dueDateString?: string): { isOverdue: boolean; label: string } {
  if (!dueDateString) return { isOverdue: false, label: 'No due date' };
  const dueDate = new Date(dueDateString);
  const now = new Date('2026-09-17T19:00:00');
  const diffTime = dueDate.getTime() - now.getTime();
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays < 0) {
    return { isOverdue: true, label: `${Math.abs(diffDays)}d overdue` };
  } else if (diffDays === 0) {
    return { isOverdue: false, label: 'Due today' };
  } else if (diffDays === 1) {
    return { isOverdue: false, label: 'Due tomorrow' };
  } else {
    return { isOverdue: false, label: `Due in ${diffDays} days` };
  }
}
