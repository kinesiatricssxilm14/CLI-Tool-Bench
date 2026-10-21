#!/usr/bin/env node

const { program } = require('./lib/cli');
const { scanDirectory } = require('./lib/scanner');

program.parse(process.argv);