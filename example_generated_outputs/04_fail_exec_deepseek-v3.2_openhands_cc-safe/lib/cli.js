const { Command } = require('commander');
const { scanDirectory } = require('./scanner');

const program = new Command();

program
  .name('sec-scanner')
  .description('A security scanner for .claude/settings.json files')
  .version('1.0.0');

program
  .argument('<directory>', 'directory to scan')
  .option('--no-low', 'filter out low severity findings')
  .action((directory, options) => {
    const result = scanDirectory(directory, options);
    process.exit(result.exitCode);
  });

// Handle missing directory argument
program.on('command:*', () => {
  console.error('Error: Missing required argument <directory>');
  program.help();
  process.exit(1);
});

module.exports = { program };