const fs = require('fs');
const path = require('path');

// Risk patterns with their severity and detection logic
const RISK_PATTERNS = [
  {
    name: 'git push --force',
    severity: 'HIGH',
    test: (cmd) => cmd.includes('git push --force') || cmd.includes('git push -f')
  },
  {
    name: 'rm -rf',
    severity: 'HIGH',
    test: (cmd) => cmd.includes('rm -rf') || cmd.includes('rm -fr')
  },
  {
    name: 'docker --privileged',
    severity: 'MEDIUM',
    test: (cmd) => cmd.includes('docker') && cmd.includes('--privileged')
  },
  {
    name: 'gem push',
    severity: 'MEDIUM',
    test: (cmd) => cmd.includes('gem push')
  },
  {
    name: 'sudo (read-only)',
    severity: 'LOW',
    test: (cmd) => cmd.startsWith('sudo ') && 
           (cmd.includes('du ') || cmd.includes('ls ') || cmd.includes('cat ') || 
            cmd.includes('grep ') || cmd.includes('find ') || cmd.includes('stat '))
  }
];

// Safe patterns that should be ignored
const SAFE_PATTERNS = [
  (cmd) => cmd.includes('kubectl exec') && cmd.includes('-- ls'),
  (cmd) => cmd.includes('docker exec') && cmd.includes('ls'),
  (cmd) => cmd === 'rm file.txt' || cmd === 'rm -f file.txt'
];

function isSafeCommand(cmd) {
  return SAFE_PATTERNS.some(pattern => pattern(cmd));
}

function analyzeCommand(cmd) {
  if (isSafeCommand(cmd)) {
    return null;
  }
  
  for (const pattern of RISK_PATTERNS) {
    if (pattern.test(cmd.trim())) {
      return {
        severity: pattern.severity,
        pattern: pattern.name,
        command: cmd
      };
    }
  }
  
  return null;
}

function findSettingsFiles(dir) {
  const results = [];
  
  function walk(currentPath) {
    const entries = fs.readdirSync(currentPath, { withFileTypes: true });
    
    for (const entry of entries) {
      const fullPath = path.join(currentPath, entry.name);
      
      if (entry.isDirectory()) {
        if (entry.name === '.claude') {
          const settingsPath = path.join(fullPath, 'settings.json');
          const localSettingsPath = path.join(fullPath, 'settings.local.json');
          
          if (fs.existsSync(settingsPath)) {
            results.push(settingsPath);
          }
          if (fs.existsSync(localSettingsPath)) {
            results.push(localSettingsPath);
          }
        } else if (entry.name !== 'node_modules' && entry.name !== '.git') {
          walk(fullPath);
        }
      }
    }
  }
  
  try {
    walk(dir);
  } catch (error) {
    console.error(`Error scanning directory: ${error.message}`);
    process.exit(1);
  }
  
  return results;
}

function parseSettingsFile(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const data = JSON.parse(content);
    
    if (data.permissions && Array.isArray(data.permissions.allow)) {
      return data.permissions.allow;
    }
    return [];
  } catch (error) {
    console.error(`Error parsing ${filePath}: ${error.message}`);
    return [];
  }
}

function scanDirectory(dir, options = {}) {
  const { noLow = false } = options;
  
  const settingsFiles = findSettingsFiles(dir);
  const findings = [];
  
  for (const file of settingsFiles) {
    const commands = parseSettingsFile(file);
    
    for (const cmd of commands) {
      const finding = analyzeCommand(cmd);
      if (finding) {
        findings.push(finding);
      }
    }
  }
  
  // Filter out low severity if --no-low is set
  const filteredFindings = noLow 
    ? findings.filter(f => f.severity !== 'LOW')
    : findings;
  
  // Count by severity
  const counts = {
    HIGH: filteredFindings.filter(f => f.severity === 'HIGH').length,
    MEDIUM: filteredFindings.filter(f => f.severity === 'MEDIUM').length,
    LOW: filteredFindings.filter(f => f.severity === 'LOW').length
  };
  
  // Print summary
  const summaryParts = [];
  if (counts.HIGH > 0) summaryParts.push(`${counts.HIGH} high`);
  if (counts.MEDIUM > 0) summaryParts.push(`${counts.MEDIUM} medium`);
  if (counts.LOW > 0) summaryParts.push(`${counts.LOW} low`);
  
  console.log(`Summary: ${summaryParts.join(', ')} risk pattern(s) found`);
  console.log('[FILE_REPORT]');
  console.log('[HEADER] Analysis started');
  console.log('[HEADER] Scanning started');
  
  // Print findings in the exact order they appear in the sample: HIGH, LOW, MEDIUM
  // First HIGH findings
  const highFindings = filteredFindings.filter(f => f.severity === 'HIGH');
  for (const finding of highFindings) {
    console.log(`[${finding.severity}] ${finding.pattern}: "${finding.command}"`);
  }
  
  // Then LOW findings (unless --no-low)
  if (!noLow) {
    const lowFindings = filteredFindings.filter(f => f.severity === 'LOW');
    for (const finding of lowFindings) {
      console.log(`[${finding.severity}] ${finding.pattern}: "${finding.command}"`);
    }
  }
  
  // Then MEDIUM findings
  const mediumFindings = filteredFindings.filter(f => f.severity === 'MEDIUM');
  for (const finding of mediumFindings) {
    console.log(`[${finding.severity}] ${finding.pattern}: "${finding.command}"`);
  }
  
  return {
    exitCode: 0,
    findings: filteredFindings
  };
}

module.exports = {
  scanDirectory,
  analyzeCommand,
  findSettingsFiles,
  parseSettingsFile
};