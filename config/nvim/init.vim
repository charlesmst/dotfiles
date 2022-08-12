call plug#begin()
" Use release branch (recommend)
Plug 'neoclide/coc.nvim', {'branch': 'release'}

" Or build from source code by using yarn: https://yarnpkg.com
Plug 'neoclide/coc.nvim', {'branch': 'master', 'do': 'yarn install --frozen-lockfile'}

Plug 'junegunn/fzf', { 'do': { -> fzf#install() } }
Plug 'junegunn/fzf.vim'
Plug 'nvim-lua/plenary.nvim'
Plug 'nvim-telescope/telescope.nvim'
Plug 'luisiacc/gruvbox-baby', {'branch': 'main'}
Plug 'overcache/NeoSolarized'
Plug 'machakann/vim-highlightedyank'
Plug 'preservim/nerdtree'
" Plug 'Xuyuanp/nerdtree-git-plugin'
Plug 'ryanoasis/vim-devicons'
Plug 'tpope/vim-commentary'

call plug#end()

set clipboard+=unnamedplus
set smartcase
set ignorecase
set relativenumber
set mouse=a
filetype plugin indent on
" show existing tab with 4 spaces width
set tabstop=4
" when indenting with '>', use 4 spaces width
set shiftwidth=4
" On pressing tab, insert 4 spaces
set expandtab


" I could not make solarized work without setting gruvbox first
colorscheme gruvbox-baby
colorscheme NeoSolarized


let g:mapleader = "\<Space>"

nnoremap <silent> <leader>h <C-w>h
nnoremap <silent> <leader>j <C-w>j
nnoremap <silent> <leader>k <C-w>k
nnoremap <silent> <leader>l <C-w>l
nnoremap <silent> <leader>p :FZF<CR>
nnoremap <silent> <leader>q :q<CR>
nnoremap <silent> <leader>w :w<CR>
inoremap <silent><expr> <c-space> coc#refresh()

nnoremap <silent> <expr> <space>e g:NERDTree.IsOpen() ? "\:NERDTreeClose<CR>" : bufexists(expand('%')) ? "\:NERDTreeFind<CR>" : "\:NERDTree<CR>"

inoremap kj <ESC>


autocmd BufEnter * if (winnr("$") == 1 && &filetype == 'coc-explorer') | q | endif
autocmd BufEnter * if (winnr("$") == 1 && &filetype == 'nerdtree') | q | endif
" Start NERDTree when Vim starts with a directory argument.
autocmd StdinReadPre * let s:std_in=1
autocmd VimEnter * if argc() == 1 && isdirectory(argv()[0]) && !exists('s:std_in') |
    \ execute 'NERDTree' argv()[0] | wincmd p | enew | execute 'cd '.argv()[0] | endif

" Find files using Telescope command-line sugar.
nnoremap <leader>ff <cmd>Telescope find_files<cr>
nnoremap <leader>fg <cmd>Telescope live_grep<cr>
nnoremap <leader>fb <cmd>Telescope buffers<cr>
nnoremap <leader>fh <cmd>Telescope help_tags<cr>

" GoTo code navigation.
nmap <silent> gd <Plug>(coc-definition)
nmap <silent> gy <Plug>(coc-type-definition)
nmap <silent> gi <Plug>(coc-implementation)
nmap <silent> gr <Plug>(coc-references)


" Some settings I got from here https://github.com/neoclide/coc.nvim
xmap <leader>fs  <Plug>(coc-format-selected)
xmap <leader>F <Cmd>:call CocAction('format')<CR>
nmap <leader>F <Cmd>:call CocAction('format')<CR>
nmap <leader>fs  <Plug>(coc-format-selected)
nmap <leader>s  <Plug>(coc-codeaction)
nmap <leader>r <Plug>(coc-rename)

inoremap <expr> <cr> pumvisible() ? "\<C-y>" : "\<C-g>u\<CR>"

" use <tab> for trigger completion and navigate to the next complete item
function! s:check_back_space() abort
  let col = col('.') - 1
  return !col || getline('.')[col - 1]  =~ '\s'
endfunction

inoremap <silent><expr> <Tab>
      \ pumvisible() ? "\<C-n>" :
      \ <SID>check_back_space() ? "\<Tab>" :
      \ coc#refresh()

inoremap <silent><expr> <cr> pumvisible() ? coc#_select_confirm() : "\<C-g>u\<CR>"
nnoremap <silent><nowait> <space>c  :<C-u>CocList commands<cr>

" Remap keys for applying codeAction to the current buffer.
nmap <leader>ac  <Plug>(coc-codeaction)
" Apply AutoFix to problem on the current line.
nmap <leader>qf  <Plug>(coc-fix-current)

" Run the Code Lens action on the current line.
nmap <leader>cl  <Plug>(coc-codelens-action)

" Use K to show documentation in preview window
nnoremap <silent> K :call <SID>show_documentation()<CR>

function! s:show_documentation()
  if (index(['vim','help'], &filetype) >= 0)
    execute 'h '.expand('<cword>')
  else
    call CocAction('doHover')
  endif
endfunction

" nnoremat <leader>ff :lua require('telescope.builtin').find_files{ find_command = {'rg', '--files', '--hidden', '-g', '!node_modules/**'} }<CR>
" search in git files
" nnoremap <leader>fr <cmd>lua require('telescope.builtin').find_files{ cwd = vim.fn.systemlist("git rev-parse --show-toplevel")[1] }<cr>
" search in git using git grepjjjk
" nnoremap <leader>gr <cmd>lua require('telescope.builtin').live_grep{ cwd = vim.fn.systemlist("git rev-parse --show-toplevel")[1] }<cr>
