/**
 * gauge.js - Renderizador Canvas de Alta Performance para Cockpit Automotivo
 */

class CircularGauge {
  constructor(canvasId, options = {}) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');

    this.min = options.min || 0;
    this.max = options.max || 7000;
    this.redline = options.redline || 6000;
    this.step = options.step || 1000;
    this.labelDivider = options.labelDivider || 1;
    this.unit = options.unit || 'RPM';

    this.currentValue = this.min;
    this.targetValue = this.min;

    // Ângulos do arco: de 135° a 405° (270° de varredura)
    this.startAngle = 0.75 * Math.PI;
    this.endAngle = 2.25 * Math.PI;

    this.setupRetina();
    this.animate();
  }

  setupRetina() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.width = rect.width || 380;
    this.height = rect.height || 380;
    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.ctx.scale(dpr, dpr);
    this.centerX = this.width / 2;
    this.centerY = this.height / 2;
    this.radius = (this.width / 2) - 28;
  }

  setValue(val) {
    this.targetValue = Math.max(this.min, Math.min(this.max, val));
  }

  animate() {
    // Interpolação suave (LERP)
    this.currentValue += (this.targetValue - this.currentValue) * 0.22;
    this.draw();
    requestAnimationFrame(() => this.animate());
  }

  draw() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);

    const totalAngle = this.endAngle - this.startAngle;
    const progress = (this.currentValue - this.min) / (this.max - this.min);
    const valueAngle = this.startAngle + (progress * totalAngle);

    // 1. Arco de Fundo
    ctx.beginPath();
    ctx.arc(this.centerX, this.centerY, this.radius, this.startAngle, this.endAngle);
    ctx.strokeStyle = '#1a2333';
    ctx.lineWidth = 14;
    ctx.lineCap = 'round';
    ctx.stroke();

    // 2. Arco Ativo Dinâmico (com gradiente)
    if (this.currentValue > this.min + 1) {
      const grad = ctx.createLinearGradient(0, this.height, this.width, 0);
      grad.addColorStop(0, '#0080ff');
      grad.addColorStop(0.7, '#00d2ff');
      if (this.currentValue >= this.redline) {
        grad.addColorStop(1, '#ff3366');
      }

      ctx.beginPath();
      ctx.arc(this.centerX, this.centerY, this.radius, this.startAngle, valueAngle);
      ctx.strokeStyle = grad;
      ctx.lineWidth = 14;
      ctx.lineCap = 'round';
      ctx.stroke();
    }

    // 3. Ticks e Marcações
    const numTicks = Math.floor((this.max - this.min) / this.step);
    for (let i = 0; i <= numTicks; i++) {
      const tickVal = this.min + (i * this.step);
      const tickAngle = this.startAngle + ((tickVal - this.min) / (this.max - this.min)) * totalAngle;

      const isRedline = tickVal >= this.redline;
      const isMajor = true;

      const innerR = this.radius - (isMajor ? 18 : 10);
      const outerR = this.radius - 24;

      const cos = Math.cos(tickAngle);
      const sin = Math.sin(tickAngle);

      ctx.beginPath();
      ctx.moveTo(this.centerX + cos * innerR, this.centerY + sin * innerR);
      ctx.lineTo(this.centerX + cos * outerR, this.centerY + sin * outerR);
      ctx.strokeStyle = isRedline ? '#ff3366' : '#4e617d';
      ctx.lineWidth = isMajor ? 2.5 : 1.5;
      ctx.stroke();

      // Rótulos de texto
      const textR = this.radius - 38;
      const textX = this.centerX + cos * textR;
      const textY = this.centerY + sin * textR + 4;
      ctx.font = '600 12px "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = isRedline ? '#ff5577' : '#829ab1';
      ctx.fillText(String(tickVal / this.labelDivider), textX, textY);
    }
  }
}
