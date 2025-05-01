document.addEventListener('DOMContentLoaded', () => {
    const bar = document.querySelector('.mobile-action-bar');
    if (!bar) return;
  
    let initialHeight = window.innerHeight;
    let isHidden = false;
  
    window.addEventListener('resize', () => {
      const newHeight = window.innerHeight;
      const keyboardVisible = newHeight < initialHeight - 150;
  
      if (keyboardVisible && !isHidden) {
        bar.style.opacity = '0';
        bar.style.pointerEvents = 'none';
        setTimeout(() => {
          bar.style.display = 'none';
        }, 200);
        isHidden = true;
      } else if (!keyboardVisible && isHidden) {
        bar.style.display = 'flex';
        setTimeout(() => {
          bar.style.opacity = '1';
          bar.style.pointerEvents = 'auto';
        }, 10);
        isHidden = false;
      }
    });
  });
  