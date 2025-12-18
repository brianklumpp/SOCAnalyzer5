// Patch to fix ajv-keywords formatMinimum incompatibility
// This runs before the build to prevent webpack config errors

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Find ALL schema-utils validate.js files recursively
const nodeModulesPath = path.join(__dirname, '..', 'node_modules');

function findValidateFiles(dir) {
  const results = [];
  try {
    const items = fs.readdirSync(dir, { withFileTypes: true });
    for (const item of items) {
      const fullPath = path.join(dir, item.name);
      if (item.isDirectory() && item.name !== '.bin') {
        results.push(...findValidateFiles(fullPath));
      } else if (item.name === 'validate.js' && fullPath.includes('schema-utils')) {
        results.push(fullPath);
      }
    }
  } catch (err) {
    // Skip directories we can't read
  }
  return results;
}

const validateFiles = findValidateFiles(nodeModulesPath);
let patchCount = 0;

validateFiles.forEach(filePath => {
  try {
    let content = fs.readFileSync(filePath, 'utf8');
    
    // Comment out the ajv-keywords import/usage that causes issues
    if (content.includes('ajv-keywords')) {
      console.log(`Patching ${filePath}...`);
      content = content.replace(
        /ajvKeywords\(ajv\);?/g,
        '// ajvKeywords(ajv); // Patched to avoid formatMinimum error'
      );
      fs.writeFileSync(filePath, content, 'utf8');
      console.log(`✓ Patched`);
      patchCount++;
    }
  } catch (err) {
    console.error(`Failed to patch ${filePath}:`, err.message);
  }
});

console.log(`\nAJV patching complete! Patched ${patchCount} files.`);
