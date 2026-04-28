(function () {
  let markmapInstance = null;
  let sourceTreeData = null;
  let sourceRoot = null;
  let currentRoot = null;
  let currentFoldLevel = null;
  let presentationMode = false;
  let presentationBranchIndex = 0;
  let presentationFocusLevel = 2;
  let presentationChildIndices = {};
  let renderVersion = 0;
  let baseRootTextWidth = 36;
  let browserWrapWidth = 28;
  let currentOptions = {
    duration: 0,
    maxWidth: 0,
    paddingX: 8,
    nodeMinHeight: 20,
    spacingVertical: 10,
    spacingHorizontal: 70,
    autoFit: false,
    embedGlobalCSS: true
  };

  const defaultOptions = { ...currentOptions };
  const defaultBrowserWrapWidth = 28;

  function showFallback(message) {
    const svg = document.getElementById('markmap-svg');
    if (svg) svg.outerHTML = '<div class="viewer-error">' + message + '</div>';
  }

  function normalizeNodeText(text) {
    return String(text || '')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n');
  }

  function wrapParagraph(paragraph, width) {
    if (!paragraph) return [''];
    const words = paragraph.trim().split(/\s+/).filter(Boolean);
    if (!words.length) return [''];

    const lines = [];
    let current = '';
    for (const word of words) {
      if (!current) {
        if (word.length <= width) {
          current = word;
        } else {
          for (let index = 0; index < word.length; index += width) {
            lines.push(word.slice(index, index + width));
          }
        }
        continue;
      }

      const candidate = `${current} ${word}`;
      if (candidate.length <= width) {
        current = candidate;
        continue;
      }

      lines.push(current);
      if (word.length <= width) {
        current = word;
      } else {
        current = '';
        for (let index = 0; index < word.length; index += width) {
          lines.push(word.slice(index, index + width));
        }
      }
    }

    if (current) lines.push(current);
    return lines.length ? lines : [''];
  }

  function wrapTextWithBreaks(text, width) {
    const paragraphs = normalizeNodeText(text).split('\n');
    const lines = [];
    for (const paragraph of paragraphs) {
      if (!paragraph) {
        lines.push('');
        continue;
      }
      lines.push(...wrapParagraph(paragraph, Math.max(4, width)));
    }
    return lines.join('<br>');
  }

  function escapeOrderedListPrefix(text) {
    return text.replace(/^(\d+)\.\s+/g, '$1\\. ');
  }

  function formatNodeContent(text, depth, rootTextWidth, maxTextWidth) {
    const width = depth === 0 ? rootTextWidth : maxTextWidth;
    return wrapTextWithBreaks(normalizeNodeText(text), width);
  }

  function markmapRootToPlainTree(node) {
    if (!node) return null;
    return {
      content: normalizeNodeText(node.content || ''),
      children: (node.children || []).map(markmapRootToPlainTree).filter(Boolean)
    };
  }

  function treeToMarkmapMarkdown(node, depth = 0, rootTextWidth = 36, maxTextWidth = 28) {
    if (!node) return '';
    if (depth === 0 && !normalizeNodeText(node.content).trim() && node.children?.length) {
      return node.children
        .map((child) => treeToMarkmapMarkdown(child, 0, rootTextWidth, maxTextWidth))
        .filter(Boolean)
        .join('\n');
    }

    const indent = '  '.repeat(depth);
    const content = escapeOrderedListPrefix(formatNodeContent(node.content, depth, rootTextWidth, maxTextWidth));
    const lines = [`${indent}- ${content}`];
    for (const child of node.children || []) lines.push(treeToMarkmapMarkdown(child, depth + 1, rootTextWidth, maxTextWidth));
    return lines.join('\n');
  }

  function assignColors(node, depth = 0) {
    const colors = ['#5E35B1', '#1E88E5', '#43A047', '#FB8C00', '#E53935', '#8E24AA', '#00ACC1'];
    if (!node.payload) node.payload = {};
    node.payload.color = colors[depth % colors.length];
    (node.children || []).forEach((child) => assignColors(child, depth + 1));
    return node;
  }

  function rebuildSourceRoot() {
    if (!sourceTreeData) {
      sourceRoot = null;
      return;
    }

    const markmapContent = treeToMarkmapMarkdown(sourceTreeData, 0, baseRootTextWidth, Math.max(4, browserWrapWidth));
    const transformer = new window.markmap.Transformer();
    const { root } = transformer.transform(markmapContent);
    sourceRoot = assignColors(root);
  }

  function cloneNode(node) {
    if (!node) return null;
    return {
      ...node,
      payload: node.payload ? { ...node.payload } : undefined,
      state: node.state ? { ...node.state } : undefined,
      children: (node.children || []).map(cloneNode)
    };
  }

  function clearFoldFlags(node) {
    if (!node) return node;
    if (node.payload?.fold) delete node.payload.fold;
    (node.children || []).forEach(clearFoldFlags);
    return node;
  }

  function applyFoldLevel(node, foldLevel, depth = 1) {
    if (!node) return node;
    if (!node.payload) node.payload = {};
    if ((node.children || []).length && foldLevel && depth >= foldLevel) {
      node.payload.fold = 1;
    } else if (node.payload.fold) {
      delete node.payload.fold;
    }
    (node.children || []).forEach((child) => applyFoldLevel(child, foldLevel, depth + 1));
    return node;
  }

  function getPresentationCandidatePaths(root, targetLevel = presentationFocusLevel) {
    const paths = [];
    function walk(node, depth, indexPath) {
      if (depth === targetLevel) {
        paths.push(indexPath);
        return;
      }
      (node.children || []).forEach((child, childIndex) => walk(child, depth + 1, [...indexPath, childIndex]));
    }
    if (root) walk(root, 1, []);
    return paths;
  }

  function pathKey(indexPath) {
    return indexPath.join('/');
  }

  function getCurrentPresentationIndexPath(root, targetLevel = presentationFocusLevel) {
    if (!root) return [];
    const branches = root.children || [];
    if (!branches.length || targetLevel < 2) return [];

    presentationBranchIndex = ((presentationBranchIndex % branches.length) + branches.length) % branches.length;
    const indexPath = [presentationBranchIndex];
    let current = branches[presentationBranchIndex];
    for (let level = 3; level <= targetLevel; level += 1) {
      const children = current.children || [];
      if (!children.length) break;
      const currentIndex = ((presentationChildIndices[level] || 0) % children.length + children.length) % children.length;
      presentationChildIndices[level] = currentIndex;
      indexPath.push(currentIndex);
      current = children[currentIndex];
    }
    return indexPath;
  }

  function applyPresentationIndexPath(indexPath) {
    if (!indexPath.length) return;
    presentationBranchIndex = indexPath[0];
    presentationChildIndices = {};
    indexPath.slice(1).forEach((childIndex, index) => {
      presentationChildIndices[index + 3] = childIndex;
    });
  }

  function getPresentationNodeByPath(root, indexPath) {
    let current = root;
    for (const childIndex of indexPath) {
      const children = current?.children || [];
      if (!children[childIndex]) return null;
      current = children[childIndex];
    }
    return current || null;
  }

  function getPresentationPathNodes(root) {
    if (!root) return [];
    const indexPath = getCurrentPresentationIndexPath(root);
    const pathNodes = [root];
    let current = root;
    for (const childIndex of indexPath) {
      const children = current.children || [];
      if (!children[childIndex]) break;
      current = children[childIndex];
      pathNodes.push(current);
    }
    return pathNodes;
  }

  function getActivePresentationNode(root, level = presentationFocusLevel) {
    return getPresentationNodeByPath(root, getCurrentPresentationIndexPath(root, level));
  }

  function collectPresentationSubtree(node, bucket) {
    if (!node) return;
    bucket.add(node);
    (node.children || []).forEach((child) => collectPresentationSubtree(child, bucket));
  }

  function applyPresentationMode(root) {
    const pathNodes = getPresentationPathNodes(root);
    const activeNode = getActivePresentationNode(root);
    if (!pathNodes.length || !activeNode) return root;

    const allowedNodes = new Set(pathNodes);
    collectPresentationSubtree(activeNode, allowedNodes);

    function walk(node) {
      if (!node || !(node.children || []).length) return;
      if (!node.payload) node.payload = {};
      if (!allowedNodes.has(node)) {
        node.payload.fold = 1;
        return;
      }
      delete node.payload.fold;
      (node.children || []).forEach(walk);
    }

    walk(root);
    return root;
  }

  function buildRenderedRoot() {
    const clonedRoot = cloneNode(sourceRoot);
    if (!clonedRoot) return null;
    clearFoldFlags(clonedRoot);
    if (presentationMode) return applyPresentationMode(clonedRoot);
    if (!currentFoldLevel) return clonedRoot;
    return applyFoldLevel(clonedRoot, currentFoldLevel);
  }

  function updateFoldStatus() {
    const status = document.getElementById('fold-status');
    if (!status) return;
    if (presentationMode) {
      status.textContent = `Режим презентации: уровень ${presentationFocusLevel}. 2-5 меняют глубину, N/P листают`;
    } else if (currentFoldLevel === null) {
      status.textContent = 'Все уровни раскрыты. 2-5 задают видимую глубину, 0 раскрывает всё';
    } else {
      status.textContent = `Видимость до уровня ${currentFoldLevel}. 0 раскрывает всё`;
    }
  }

  function updatePresentationStatus() {
    const status = document.getElementById('presentation-status');
    const button = document.getElementById('presentation-toggle');
    if (!status || !button) return;
    if (!presentationMode) {
      status.textContent = 'Презентация выключена. M включает, N/P листают ветки';
      button.textContent = 'Презентация';
      return;
    }

    const candidatePaths = getPresentationCandidatePaths(sourceRoot);
    const currentPath = pathKey(getCurrentPresentationIndexPath(sourceRoot));
    const currentIndex = Math.max(0, candidatePaths.findIndex((item) => pathKey(item) === currentPath));
    const activeNode = getActivePresentationNode(sourceRoot);
    if (!candidatePaths.length || !activeNode) {
      status.textContent = `Нет узлов уровня ${presentationFocusLevel}`;
      button.textContent = 'Выйти';
      return;
    }

    const branchTitle = activeNode.content || `Узел ${currentIndex + 1}`;
    status.textContent = `Презентация L${presentationFocusLevel}: ${currentIndex + 1}/${candidatePaths.length} - ${branchTitle}`;
    button.textContent = 'Выйти';
  }

  function getCurrentTransform() {
    if (!markmapInstance) return null;
    const svg = document.getElementById('markmap-svg');
    const group = svg?.querySelector('g');
    const transform = group?.getAttribute('transform');
    if (!transform) return null;
    const match = transform.match(/translate\(([^,]+),([^)]+)\)\s*scale\(([^)]+)\)/);
    if (!match) return null;
    return { x: parseFloat(match[1]), y: parseFloat(match[2]), scale: parseFloat(match[3]) };
  }

  function applyTransform(transform) {
    if (!transform || !markmapInstance) return;
    const svg = document.getElementById('markmap-svg');
    const group = svg?.querySelector('g');
    if (group) group.setAttribute('transform', `translate(${transform.x},${transform.y}) scale(${transform.scale})`);
  }

  function applyPresentationStyling() {
    const svg = document.getElementById('markmap-svg');
    if (!svg || !currentRoot) return;

    const activeNode = presentationMode ? getActivePresentationNode(currentRoot) : null;
    const activePaths = new Set();
    if (presentationMode && activeNode) {
      const activeNodes = new Set();
      getPresentationPathNodes(currentRoot).forEach((node) => activeNodes.add(node));
      collectPresentationSubtree(activeNode, activeNodes);
      activeNodes.forEach((node) => {
        if (node?.state?.path) activePaths.add(node.state.path);
      });
    }

    svg.querySelectorAll('path.markmap-link').forEach((element) => {
      const nodePath = element.getAttribute('data-path');
      const shouldDim = Boolean(presentationMode && activeNode && nodePath && !activePaths.has(nodePath));
      element.style.opacity = shouldDim ? '0.22' : '1';
      element.style.strokeOpacity = shouldDim ? '0.22' : '1';
    });

    svg.querySelectorAll('g.markmap-node').forEach((group) => {
      const nodePath = group.getAttribute('data-path');
      const shouldDim = Boolean(presentationMode && activeNode && nodePath && !activePaths.has(nodePath));
      const textOpacity = shouldDim ? '0.42' : '1';
      const lineOpacity = shouldDim ? '0.22' : '1';
      const foreignObject = group.querySelector('foreignObject');
      const foreignContent = foreignObject?.querySelector('div');
      const line = group.querySelector('line');
      const circle = group.querySelector('circle');
      if (foreignObject) foreignObject.style.opacity = textOpacity;
      if (foreignContent) foreignContent.style.opacity = textOpacity;
      if (line) {
        line.style.opacity = lineOpacity;
        line.style.strokeOpacity = lineOpacity;
      }
      if (circle) {
        circle.style.opacity = lineOpacity;
        circle.style.strokeOpacity = lineOpacity;
        circle.style.fillOpacity = lineOpacity;
      }
    });
  }

  function waitForNextFrame() {
    return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }

  function centerPresentationBranchVertically() {
    if (!presentationMode || !markmapInstance || !currentRoot) return;
    const branch = getActivePresentationNode(currentRoot);
    if (!branch || typeof markmapInstance.findElement !== 'function') return;
    const svg = document.getElementById('markmap-svg');
    const elementInfo = markmapInstance.findElement(branch);
    const currentTransform = getCurrentTransform();
    if (!svg || !elementInfo?.g || !currentTransform) return;

    const svgRect = svg.getBoundingClientRect();
    const branchRect = elementInfo.g.getBoundingClientRect();
    if (!svgRect.height || !branchRect.height) return;
    const deltaY = (svgRect.top + svgRect.height / 2) - (branchRect.top + branchRect.height / 2);
    if (Math.abs(deltaY) >= 1) applyTransform({ ...currentTransform, y: currentTransform.y + deltaY });
  }

  async function updateMarkmap() {
    rebuildSourceRoot();
    currentRoot = buildRenderedRoot();
    if (!currentRoot) return;

    const svg = document.getElementById('markmap-svg');
    if (!svg) return;

    const savedTransform = getCurrentTransform();
    const currentRenderVersion = ++renderVersion;
    svg.innerHTML = '';
    markmapInstance = window.markmap.Markmap.create(svg, {
      ...currentOptions,
      color: (node) => node.payload?.color || '#5E35B1'
    });
    await Promise.resolve(markmapInstance.setData(currentRoot));
    if (currentRenderVersion !== renderVersion) return;

    updateFoldStatus();
    updatePresentationStatus();
    applyPresentationStyling();
    if (savedTransform) applyTransform(savedTransform);
    else markmapInstance.fit();

    await waitForNextFrame();
    if (currentRenderVersion !== renderVersion) return;
    centerPresentationBranchVertically();
    applyPresentationStyling();
  }

  function togglePresentationMode() {
    if (!sourceRoot) return;
    presentationMode = !presentationMode;
    if (presentationMode) {
      currentFoldLevel = null;
      presentationFocusLevel = 2;
      presentationBranchIndex = 0;
      presentationChildIndices = {};
    }
    updateMarkmap();
  }

  function setPresentationFocusLevel(level) {
    if (!sourceRoot) return;
    if (!presentationMode) {
      toggleFoldLevel(level);
      return;
    }

    presentationFocusLevel = level;
    const candidates = getPresentationCandidatePaths(sourceRoot, level);
    if (!candidates.length) {
      updateMarkmap();
      return;
    }

    const currentPath = getCurrentPresentationIndexPath(sourceRoot, level);
    const exactMatch = candidates.find((candidate) => pathKey(candidate) === pathKey(currentPath));
    if (exactMatch) {
      applyPresentationIndexPath(exactMatch);
      updateMarkmap();
      return;
    }

    const prefixMatch = candidates.find((candidate) => currentPath.every((part, index) => candidate[index] === part));
    applyPresentationIndexPath(prefixMatch || candidates[0]);
    updateMarkmap();
  }

  function stepPresentationBranch(direction) {
    if (!presentationMode || !sourceRoot) return;
    const candidatePaths = getPresentationCandidatePaths(sourceRoot);
    if (!candidatePaths.length) return;
    const currentPath = pathKey(getCurrentPresentationIndexPath(sourceRoot));
    const currentIndex = candidatePaths.findIndex((item) => pathKey(item) === currentPath);
    const nextIndex = ((currentIndex >= 0 ? currentIndex : 0) + direction + candidatePaths.length) % candidatePaths.length;
    applyPresentationIndexPath(candidatePaths[nextIndex]);
    updateMarkmap();
  }

  function toggleFoldLevel(level) {
    if (!sourceRoot) return;
    if (presentationMode) presentationMode = false;
    if (currentFoldLevel === null) currentFoldLevel = level;
    else if (currentFoldLevel >= level) currentFoldLevel = level - 1;
    else currentFoldLevel = level;
    updateMarkmap();
  }

  function initializeSettings() {
    document.getElementById('settings-toggle')?.addEventListener('click', () => {
      document.getElementById('settings-panel')?.classList.toggle('active');
    });
    document.getElementById('close-settings')?.addEventListener('click', () => {
      document.getElementById('settings-panel')?.classList.remove('active');
    });
    document.getElementById('presentation-toggle')?.addEventListener('click', togglePresentationMode);
    document.getElementById('zoom-in')?.addEventListener('click', () => markmapInstance?.rescale(1.25));
    document.getElementById('zoom-out')?.addEventListener('click', () => markmapInstance?.rescale(0.8));
    document.getElementById('fit-button')?.addEventListener('click', () => markmapInstance?.fit());

    const sliders = [
      { id: 'duration', key: 'duration' },
      { id: 'nodeMinHeight', key: 'nodeMinHeight' },
      { id: 'spacingVertical', key: 'spacingVertical' },
      { id: 'spacingHorizontal', key: 'spacingHorizontal' }
    ];

    sliders.forEach(({ id, key }) => {
      const slider = document.getElementById(`${id}-slider`);
      const value = document.getElementById(`${id}-value`);
      if (!slider || !value) return;
      slider.value = currentOptions[key];
      value.textContent = currentOptions[key];
      slider.addEventListener('input', () => {
        value.textContent = slider.value;
        currentOptions[key] = parseInt(slider.value, 10);
        updateMarkmap();
      });
    });

    const wrapWidthSlider = document.getElementById('wrapWidth-slider');
    const wrapWidthValue = document.getElementById('wrapWidth-value');
    if (wrapWidthSlider && wrapWidthValue) {
      wrapWidthSlider.value = browserWrapWidth;
      wrapWidthValue.textContent = browserWrapWidth;
      wrapWidthSlider.addEventListener('input', () => {
        wrapWidthValue.textContent = wrapWidthSlider.value;
        browserWrapWidth = parseInt(wrapWidthSlider.value, 10);
        updateMarkmap();
      });
    }

    document.getElementById('reset-settings')?.addEventListener('click', () => {
      currentOptions = { ...defaultOptions };
      browserWrapWidth = defaultBrowserWrapWidth;
      sliders.forEach(({ id, key }) => {
        const slider = document.getElementById(`${id}-slider`);
        const value = document.getElementById(`${id}-value`);
        if (!slider || !value) return;
        slider.value = defaultOptions[key];
        value.textContent = defaultOptions[key];
      });
      if (wrapWidthSlider && wrapWidthValue) {
        wrapWidthSlider.value = defaultBrowserWrapWidth;
        wrapWidthValue.textContent = defaultBrowserWrapWidth;
      }
      updateMarkmap();
    });
  }

  function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', (event) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target;
      if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return;

      if (['2', '3', '4', '5'].includes(event.key)) {
        event.preventDefault();
        if (presentationMode) setPresentationFocusLevel(Number(event.key));
        else toggleFoldLevel(Number(event.key));
        return;
      }

      if (event.key === '0' || event.key === 'Escape') {
        if (!currentFoldLevel && !presentationMode) return;
        event.preventDefault();
        currentFoldLevel = null;
        presentationMode = false;
        updateMarkmap();
        return;
      }

      if (event.key === 'n' || event.key === 'N' || event.key === 'т' || event.key === 'Т') {
        if (!presentationMode) return;
        event.preventDefault();
        stepPresentationBranch(1);
        return;
      }

      if (event.key === 'p' || event.key === 'P' || event.key === 'з' || event.key === 'З') {
        if (!presentationMode) return;
        event.preventDefault();
        stepPresentationBranch(-1);
        return;
      }

      if (event.key === 'm' || event.key === 'M' || event.key === 'ь' || event.key === 'Ь') {
        event.preventDefault();
        togglePresentationMode();
      }
    });
  }

  async function initializeCourseMarkmap() {
    try {
      if (!window.markmap || !window.markmap.Transformer || !window.markmap.Markmap) {
        showFallback('Не удалось загрузить локальные markmap-библиотеки.');
        return;
      }

      const source = String(window.courseMarkmapSource || '').trim();
      if (!source) {
        showFallback('Источник карты пуст.');
        return;
      }

      const transformer = new window.markmap.Transformer();
      const { root } = transformer.transform(source);
      sourceTreeData = markmapRootToPlainTree(root);
      initializeSettings();
      initializeKeyboardShortcuts();
      await updateMarkmap();
    } catch (error) {
      showFallback('Ошибка построения карты: ' + error.message);
    }
  }

  window.addEventListener('load', initializeCourseMarkmap);
}());
