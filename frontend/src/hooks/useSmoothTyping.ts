import { useState, useEffect, useRef } from 'react';

/**
 * 实现打字机效果的平滑输出 Hook
 * @param targetContent 目标完整内容（从后端接收的真实数据）
 * @param isThinking 是否正在生成中（可选，用于优化历史消息显示）
 * @returns displayedContent 当前应该显示的内容
 */
export function useSmoothTyping(targetContent: string, isThinking?: boolean) {
  const [displayedContent, setDisplayedContent] = useState("");
  const isFirstRender = useRef(true);
  const animatingRef = useRef(false);
  
  // 记录当前显示的长度，用于在 animationFrame 中引用（避免闭包陷阱）
  // 这里的长度是指“已经渲染到屏幕上的长度”
  const displayedLengthRef = useRef(0);
  
  // 记录已经处理过的 targetContent 长度（避免重复入队）
  const processedLengthRef = useRef(0);
  
  // 队列：存储还没有显示出来的字符
  const queueRef = useRef<string[]>([]);

  useEffect(() => {
    // 1. 初始化判断：如果是首次渲染且内容很长，说明是历史消息，直接显示，不搞打字机
    if (isFirstRender.current) {
      isFirstRender.current = false;
      if (targetContent.length > 0 && !isThinking) {
        setDisplayedContent(targetContent);
        displayedLengthRef.current = targetContent.length;
        processedLengthRef.current = targetContent.length;
        return;
      }
    }

    // 2. 计算新增内容并入队
    // 使用 processedLengthRef 来计算增量，而不是 displayedLengthRef
    const prevProcessedLen = processedLengthRef.current;
    const nextLen = targetContent.length;

    if (nextLen > prevProcessedLen) {
      const deltaString = targetContent.slice(prevProcessedLen);
      const chars = deltaString.split('');
      queueRef.current.push(...chars);
      processedLengthRef.current = nextLen;
    } else if (nextLen < prevProcessedLen) {
      // 异常情况（比如清空对话）：直接重置
      setDisplayedContent(targetContent);
      displayedLengthRef.current = nextLen;
      processedLengthRef.current = nextLen;
      queueRef.current = [];
    }

    // 3. 启动渲染循环
    const renderLoop = () => {
      if (queueRef.current.length === 0) {
        animatingRef.current = false;
        return;
      }

      animatingRef.current = true;

      // --- 动态速率控制核心算法 ---
      const queueLength = queueRef.current.length;
      let consumeCount = 1;

      if (queueLength > 200) consumeCount = 20;      // 积压极多，狂奔
      else if (queueLength > 50) consumeCount = 5;   // 积压较多，加速
      else if (queueLength > 10) consumeCount = 2;   // 略有积压，小跑
      // 否则 consumeCount = 1 (匀速)

      const charsToRender = queueRef.current.splice(0, consumeCount).join('');
      
      setDisplayedContent(prev => {
        const next = prev + charsToRender;
        displayedLengthRef.current = next.length;
        return next;
      });

      requestAnimationFrame(renderLoop);
    };

    if (!animatingRef.current && queueRef.current.length > 0) {
      renderLoop();
    }

  }, [targetContent, isThinking]);

  return displayedContent;
}

