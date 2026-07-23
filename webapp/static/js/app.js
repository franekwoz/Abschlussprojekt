document.querySelectorAll('form[data-submit]').forEach(f=>f.addEventListener('submit',()=>{const b=f.querySelector('button');if(b){b.disabled=true;b.textContent='Wird berechnet…'}}));
