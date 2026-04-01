const DEFAULT_DELAY = 120;

export function request(handler, { delay = DEFAULT_DELAY } = {}) {
  return new Promise((resolve, reject) => {
    window.setTimeout(() => {
      Promise.resolve()
        .then(handler)
        .then((data) => resolve({ code: 0, message: 'ok', data }))
        .catch((error) => reject(error));
    }, delay);
  });
}
